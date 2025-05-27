#!/usr/bin/env python3
import os
import sys
import requests
from readability import Document
from bs4 import BeautifulSoup
from ollama import chat
from ollama._types import ChatResponse
from dataclasses import dataclass, field
from typing import List, Dict
import asyncio
from crawl4ai import AsyncWebCrawler
import sys_msgs

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

class NewsAgent:
    def __init__(self, config: SearchAgentConfig):
        if not config.search_url:
            raise ValueError("SEARCH_URL must be set in environment or config.")
        self.search_url = config.search_url
        self.model_name = config.model_name
        self.headers = config.headers
        self.max_urls = config.max_urls

    def get_news_urls(self, query: str) -> List[str]:
        """
        Query the search API and return a list of news URLs (limited by max_urls).
        """
        resp = requests.get(
            f"{self.search_url}?q={requests.utils.quote(query)}&format=json"
        )
        resp.raise_for_status()
        data = resp.json()
        urls = [item.get("url") for item in data.get("results", []) if item.get("url")]
        return urls[: self.max_urls]

#    def html_to_text(self, html: str) -> str:
#        """
#        Extracts the main article content from HTML using Mozilla Readability,
#        then returns clean plain text.
#        """
#        doc = Document(html)
#        summary_html = doc.summary()
#        print(doc.get_clean_html())
#        soup = BeautifulSoup(summary_html, "html.parser")
#        return soup.get_text(separator=" ", strip=True)

    def html_to_text(self, html: str) -> str:
        """
        Extracts all textual content from HTML by removing scripts/styles and returning plain text.
        """
        soup = BeautifulSoup(html, "html.parser")
        # remove script and style elements
        for tag in soup(["script", "style", "header", "footer", "nav", "form", "noscript"]):
            tag.decompose()
        # get all text
        text = soup.get_text(separator=" ", strip=True)
        return text


#    def get_cleaned_text(self, urls: List[str]) -> List[str]:
#        """
#        Fetch each URL and return cleaned text snippets prefixed with source metadata.
#        """
#        texts: List[str] = []
#        for url in urls:
#            print(f"Fetching {url}")
#            try:
#                resp = requests.get(url, headers=self.headers, timeout=10)
#                resp.raise_for_status()
#            except requests.RequestException as e:
#                print(f"Failed to fetch {url}: {e}")
#                continue
#            content = self.html_to_text(resp.text)
#            texts.append(f"**Source:** {url}\n\n{content}\n\n")
#        return texts

    def get_cleaned_text(self, urls: List[str]) -> List[str]:
        """
        Uses Crawl4AI to asynchronously crawl each URL and returns a list of
        Markdown-formatted text snippets prefixed with source metadata.
        """
        return asyncio.run(self._crawl_urls(urls))

    async def _crawl_urls(self, urls: List[str]) -> List[str]:
        texts = []
        # Crawl4AI’s AsyncWebCrawler context manager
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                print(f"Crawling {url} with Crawl4AI")
                try:
                    result = await crawler.arun(url=url)
                    # .markdown contains the content in markdown format
                    texts.append(f"**Source:** {url}\n\n{result.markdown}\n\n")
                except Exception as e:
                    print(f"Error crawling {url}: {e}")
        return texts


    def answer_query(self, query: str, texts: List[str]) -> str:
        """
        Sends the query and article texts to the LLM and returns a Markdown-formatted answer.
        """
        prompt = (
#            f"SEARCH_MESSAGE:\n{query}\n\n"
#            f"Use only the following content to answer. Provide the response in Markdown format.\n\n"
            "SEARCH_RESULTS:\n".join(texts)
        )
        
        sys_msg=(
                " I want you to answer as concisely and precisely as possible to the following SEARCH_MESSAGE: \n{query}\n\n"
                "To do so you need to analyze the text that you get after SEARCH_RESULTS which is obtained from parsing the text of websites. "
                "Look meticolously into SEARCH_RESULTS to only answer to the SEARCH_MESSAGE. "
                "Provide the response in Markdown format.\n\n"
                )

        print(texts)
#        messages = [{"role": "user", "content": prompt}]
        messages=[
            {'role': 'system', 'content': sys_msg},
            {'role': 'user',   'content': prompt}
        ]

        resp: ChatResponse = chat(model=self.model_name, messages=messages)
        # Extract generated text
        #answer = getattr(resp, "response", str(resp))
        answer = resp['message']['content']
        #print(resp.message)
        return answer


def run_agent(query: str) -> None:
    """
    Initializes the NewsAgent with default config, runs the search+summarization pipeline,
    and prints the Markdown-formatted answer.
    """
    config = SearchAgentConfig()
    agent = NewsAgent(config)
    urls = agent.get_news_urls(query)
    texts = agent.get_cleaned_text(urls)
#    print(texts)
    answer_md = agent.answer_query(query, texts)
    print(answer_md)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: main.py [query]")
        sys.exit(1)
    query = " ".join(sys.argv[1:])
    run_agent(query)

if __name__ == "__main__":
    main()

