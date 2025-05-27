#!/usr/bin/env python3
import os
import sys
import requests
from readability import Document
from bs4 import BeautifulSoup
from ollama import chat
from ollama._types import ChatResponse

# Retrieve search endpoint from environment
SEARCH_URL = os.getenv("SEARCH_URL")

# Common headers to avoid 403 responses
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}


def get_news_urls(query: str) -> list[str]:
    """
    Query the search API and return a list of news URLs (limit 1).
    """
    response = requests.get(f"{SEARCH_URL}?q={query}&format=json")
    response.raise_for_status()
    data = response.json()
    return [item["url"] for item in data.get("results", [])][:1]


def html_to_text(html: str) -> str:
    """
    Use Mozilla Readability to parse the article content,
    then clean it with BeautifulSoup to plain text.
    """
    doc = Document(html)
    summary_html = doc.summary()
    soup = BeautifulSoup(summary_html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def get_cleaned_text(urls: list[str]) -> list[str]:
    """
    Fetch each URL and return cleaned text snippets with source headers.
    """
    texts = []
    for url in urls:
        print(f"Fetching {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue
        content = html_to_text(resp.text)
        texts.append(f"Source: {url}\n{content}\n\n")
    return texts


def answer_query(query: str, texts: list[str]) -> None:
    """
    Send the combined texts and query to Ollama via the Python client and print the response.
    """
    prompt = (
        f"{query}. Summarize the information and provide an answer in markdown format. "
        f"Use only the information in the following articles to answer the question:\n"
        + "".join(texts)
    )
    # Use Python Ollama client instead of subprocess
    messages = [{"role": "user", "content": prompt}]
    resp: ChatResponse = chat(model="llama3.2:latest", messages=messages)
    # Print the assistant's reply
    try:
        # assuming resp has an attribute 'response' with the generated text
        print(resp.response)
    except AttributeError:
        # fallback: print full object
        print(resp)


def main() -> None:
    if not SEARCH_URL:
        print("ERROR: Please set the SEARCH_URL environment variable.")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    if not query:
        print("Usage: main.py [query]")
        sys.exit(1)

    print(f"Query: {query}")
    urls = get_news_urls(query)
    texts = get_cleaned_text(urls)
    answer_query(query, texts)


if __name__ == "__main__":
    main()

