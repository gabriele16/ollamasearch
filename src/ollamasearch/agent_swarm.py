#!/usr/bin/env python3
import os
import sys
import requests
import requests.utils
import argparse
import yaml
import asyncio
from dataclasses import dataclass, field
from typing import Union, Any, List, Dict, Optional
from ollama import chat
from ollama._types import ChatResponse
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import BM25ContentFilter

@dataclass
class SearchAgentConfig:
    query: str
    ollama_options: Dict[str, Any] = field(default_factory=dict)
    stream: bool = True
    search_url: str = os.getenv("SEARCH_URL", "")
    model_name: str = "llama3.2:latest"
    headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/117.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    })
    max_urls: int = 1

@dataclass
class SwarmConfig(SearchAgentConfig):
    max_iterations: int = 2  # how many loops to simplify

class Agent:
    def __init__(self, config: SearchAgentConfig):
        if not config.search_url:
            raise ValueError("SEARCH_URL must be set in environment or config.")
        self.search_url = config.search_url
        self.model_name = config.model_name
        self.headers = config.headers
        self.max_urls = config.max_urls
        self.ollama_options = config.ollama_options
        self.stream = config.stream
        self.query = config.query

    def _extract_content(
        self,
        stream_or_resp: Union[ChatResponse, Any]
    ) -> str:
        """
        If streaming is enabled, drain the generator and concatenate
        each chunk['message']['content']. Otherwise return the single
        ChatResponse content.
        """
        if self.stream:
            full_answer = ""
            for chunk in stream_or_resp:
                full_answer += chunk['message']['content']
            return full_answer
        else:
            return stream_or_resp['message']['content']


    def get_news_urls(self, query: str) -> List[str]:
        resp = requests.get(
            f"{self.search_url}?q={requests.utils.quote(query)}&format=json"
        )
        resp.raise_for_status()
        data = resp.json()
        urls = [item.get("url") for item in data.get("results", []) if item.get("url")]
        return urls[: self.max_urls]

    def get_cleaned_text(self, urls: List[str]) -> List[str]:
        return asyncio.run(self._crawl_urls(urls))

    async def _crawl_urls(self, urls: List[str]) -> List[str]:

#        config = CrawlerRunConfig(
#           word_count_threshold=5,        # Minimum words per content block
#           exclude_external_links=True,    # Remove external links
#           remove_overlay_elements=True,   # Remove popups/modals
#           process_iframes=True           # Process iframe content
#        )
        
        config = CrawlerRunConfig(
           # Content filtering
           word_count_threshold=10,
           excluded_tags=['form', 'header'],
           exclude_external_links=True,
           # Content processing
           process_iframes=True,
           remove_overlay_elements=True,
           # Cache control
        )        
     
        texts = []        
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                print(f"Crawling {url} with Crawl4AI")
                try:
                    result = await crawler.arun(url=url,config=config)
                    texts.append(f"{result.markdown.raw_markdown}")
                    if not result.success:
                       print(f"Crawl failed: {result.error_message}")
                       print(f"Status code: {result.status_code}")                    
                except Exception as e:
                    print(f"Error crawling {url}: {e}")
        return texts

    def answer_query(self, query: str, texts: List[str]) -> str:
        sys_prompt = (
            f"I want you to answer the question '{query}' "
            "based on raw search results from websites in Markdown. "
            "Please answer the question concisely in Markdown, without asking further questions."
        )
        texts_joined = "\n---\n".join(texts)
        user_prompt = f"web search results:{texts_joined}"
        messages = [{"role": "system", "content": sys_prompt},
                   {"role": "user", "content": user_prompt}]
        resp: ChatResponse = chat(model=self.model_name, options=self.ollama_options,
                stream=self.stream, messages=messages)

        return self._extract_content(resp)

class AgentSwarm(Agent):
    def __init__(self, config: SwarmConfig):
        super().__init__(config)
        self.max_iterations = config.max_iterations

    def should_search(self, query: str) -> bool:
        return True

    def check_answer(self, query: str, answer: str) -> bool:
        sys_prompt = (
            f"You are an evaluator. Question: '{query}'. Take the provided answer and judge if it fully addresses the question. "
            "Respond with YES or NO only."
        )
        resp: ChatResponse = chat(
            model=self.model_name,
            stream=False,
            options=self.ollama_options,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": answer}
            ]
        )
        verdict = resp['message']['content'].strip().upper()
        return verdict.startswith("YES")

    def simplify_results(self, query: str, texts: List[str]) -> List[str]:
        prompt = (
            f"Simplify and highlight the most relevant parts of the following search results for the question '{query}':\n\n"
            + "\n---\n".join(texts)
            + "\nReturn the result in concise Markdown."
        )
        resp: ChatResponse = chat(model=self.model_name,
                stream=self.stream,
                options=self.ollama_options,
                messages=[{"role": "user", "content": prompt}
        ])
        simplified = self._extract_content(resp)
        return [f"**Simplified Results:**\n\n{simplified}\n\n"]

    def run(self, query: str) -> str:
        if not self.should_search(query):
            return "No search performed."
        print("Performing a websearch to answer the following question")
        print(query)
        urls = self.get_news_urls(query)
        texts = self.get_cleaned_text(urls)
        print(f"\nHere's all I have found in this web search")
        texts_joined = "\n---\n".join(texts)
        print(texts_joined)
        print("Now I am processing the text above to evaluate the user's question")
        answer = self.answer_query(query, texts)
        print(f"Here's an elaboration of the question:\n{answer}\n")
        print(f"Did I answer successfully?")
        if self.check_answer(query, answer):
            print("YES")
            return answer
        if self.max_iterations >1:
            print(f"NO\n.I will try to improve my answer for {self.max_iterations - 1} iterations")
        else:
            print(f"NO\n.I tried to do a one-shot search only. Exiting...")
        for it in range(self.max_iterations - 1):
            texts = self.simplify_results(query, texts)
            print(f"Iteration #{it} to improve and simplify my answer")
            print("Rielaborated question with the following results\n {texts}")
            answer = self.answer_query(query, texts)
            print(f"Below is my last answer to the query\n{query}")
            print(answer)
            if self.check_answer(query, answer):
                return answer
        return answer


def load_config(path: str) -> SwarmConfig:
    """
    Load a YAML file into SearchAgentConfig, allowing ollama_options
    to be either a dict or a list of single-key dicts.
    """
    with open(path, 'r') as f:
        data = yaml.safe_load(f)

    raw_opts = data.get('ollama_options', {})

    # If ollama_options is a list of {"key": value}, flatten it
    if isinstance(raw_opts, list):
        merged: Dict[str, Any] = {}
        for entry in raw_opts:
            if not (isinstance(entry, dict) and len(entry) == 1):
                raise ValueError(
                    "Each item in ollama_options list must be a single-key dict"
                )
            key, val = next(iter(entry.items()))
            merged[key] = val
        data['ollama_options'] = merged

    # If it's not a dict at all (e.g. null), coerce to empty dict
    elif not isinstance(raw_opts, dict):
        data['ollama_options'] = {}

    return SwarmConfig(**data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an AgentSwarm with YAML config.")
    parser.add_argument("-c", "--config", required=True, help="Path to YAML config file.")
    parser.add_argument("-o", "--output", help="Path to output Markdown file.")
    args = parser.parse_args()

    config = load_config(args.config)
    if not config.query:
        parser.error("No query provided in config under 'query'.")
    query = config.query
    swarm = AgentSwarm(config)
    result = swarm.run(query)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Answer written to {args.output}")
    else:
        print(result)

