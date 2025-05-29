#!/usr/bin/env python3
import os
import sys
import requests
import requests.utils
import argparse
import yaml
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from ollama import chat
from ollama._types import ChatResponse
from crawl4ai import AsyncWebCrawler

@dataclass
class SearchAgentConfig:
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
    query: Optional[str] = None  # required for CLI-less query

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
        texts = []
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                print(f"Crawling {url} with Crawl4AI")
                try:
                    result = await crawler.arun(url=url)
                    texts.append(f"**Source:** {url}\n\n{result.markdown}\n\n")
                except Exception as e:
                    print(f"Error crawling {url}: {e}")
        return texts

    def answer_query(self, query: str, texts: List[str]) -> str:
        prompt = (
            f"Question: {query}\n\n"
            "Here are the search results in Markdown:\n\n"
            + "\n---\n".join(texts)
            + "\nPlease answer the question concisely in Markdown."
        )
        messages = [{"role": "user", "content": prompt}]
        resp: ChatResponse = chat(model=self.model_name, messages=messages)
        return resp['message']['content']

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
        resp: ChatResponse = chat(model=self.model_name, messages=[
            {"role": "user", "content": prompt}
        ])
        simplified = resp['message']['content']
        return [f"**Simplified Results:**\n\n{simplified}\n\n"]

    def run(self, query: str) -> str:
        if not self.should_search(query):
            return "No search performed."
        urls = self.get_news_urls(query)
        texts = self.get_cleaned_text(urls)
        answer = self.answer_query(query, texts)
        if self.check_answer(query, answer):
            return answer
        for _ in range(self.max_iterations - 1):
            texts = self.simplify_results(query, texts)
            answer = self.answer_query(query, texts)
            if self.check_answer(query, answer):
                return answer
        return answer


def load_config(path: str) -> SwarmConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
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

