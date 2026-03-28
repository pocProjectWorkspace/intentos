"""
IntentOS browser_agent — Web search and data extraction

Primitive actions:
  - search_web: search DuckDuckGo and return results
  - fetch_page: fetch a URL and return its text content
  - extract_data: fetch a URL and use the LLM to extract specific data

Follows SPEC.md: run() entry point, standard output dicts, dry_run support,
plain-language errors, audit metadata.
"""

from __future__ import annotations

import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_REQUEST_TIMEOUT = 15  # seconds
_MAX_PAGE_SIZE = 500_000  # 500 KB text limit for fetched pages
_MAX_EXTRACT_CHARS = 12_000  # chars sent to LLM for extraction


def _meta(
    files_affected: int = 0,
    bytes_affected: int = 0,
    duration_ms: int = 0,
    paths_accessed: list[str] | None = None,
) -> dict:
    return {
        "files_affected": files_affected,
        "bytes_affected": bytes_affected,
        "duration_ms": duration_ms,
        "paths_accessed": paths_accessed or [],
    }


def _error(code: str, message: str) -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "metadata": _meta(),
    }


def _get_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _clean_text(html: str) -> str:
    """Extract readable text from HTML, stripping tags and excess whitespace."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, footer elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Collapse excessive whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# search_web — DuckDuckGo HTML search (no API key needed)
# ---------------------------------------------------------------------------

def _search_web(params: dict, context: dict) -> dict:
    """Search DuckDuckGo and return top results."""
    t0 = time.monotonic()
    query = params.get("query", "").strip()

    if not query:
        return _error("MISSING_QUERY", "I need a search query to look things up")

    max_results = min(params.get("max_results", 10), 20)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would search the web for '{query}'",
            "result": {"preview": f"Search results for: {query}"},
            "metadata": _meta(),
        }

    url = "https://html.duckduckgo.com/html/"
    data = {"q": query}

    try:
        resp = requests.post(
            url,
            data=data,
            headers=_get_headers(),
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        return _error("CONNECTION_ERROR", "Could not connect to the search engine — check your internet connection")
    except requests.Timeout:
        return _error("TIMEOUT", "The search took too long — try again")
    except requests.HTTPError as e:
        return _error("SEARCH_FAILED", f"Search engine returned an error (HTTP {e.response.status_code})")
    except requests.RequestException:
        return _error("SEARCH_FAILED", "Something went wrong while searching the web")

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for item in soup.select(".result"):
        title_tag = item.select_one(".result__title a, .result__a")
        snippet_tag = item.select_one(".result__snippet")

        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")

        # DuckDuckGo wraps URLs in a redirect — extract the actual URL
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                href = urllib.parse.unquote(match.group(1))

        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

        results.append({
            "title": title,
            "url": href,
            "snippet": snippet,
        })

        if len(results) >= max_results:
            break

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Found {len(results)} result(s) for '{query}'",
        "result": results,
        "metadata": _meta(duration_ms=elapsed),
    }


# ---------------------------------------------------------------------------
# fetch_page — fetch a URL and return cleaned text
# ---------------------------------------------------------------------------

def _fetch_page(params: dict, context: dict) -> dict:
    """Fetch a URL and return its text content."""
    t0 = time.monotonic()
    url = params.get("url", "").strip()

    if not url:
        return _error("MISSING_URL", "I need a URL to fetch")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would fetch content from {url}",
            "result": {"preview": f"Page content from {url}"},
            "metadata": _meta(),
        }

    try:
        resp = requests.get(
            url,
            headers=_get_headers(),
            timeout=_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        return _error("CONNECTION_ERROR", "Could not connect to that website — check the URL and your internet connection")
    except requests.Timeout:
        return _error("TIMEOUT", "The website took too long to respond — try again")
    except requests.HTTPError as e:
        return _error("FETCH_FAILED", f"The website returned an error (HTTP {e.response.status_code})")
    except requests.RequestException:
        return _error("FETCH_FAILED", "Something went wrong while fetching that page")

    content_type = resp.headers.get("content-type", "")
    if "text/html" in content_type or "text/plain" in content_type:
        text = _clean_text(resp.text)
    else:
        text = resp.text[:_MAX_PAGE_SIZE]

    # Truncate if too large
    if len(text) > _MAX_PAGE_SIZE:
        text = text[:_MAX_PAGE_SIZE] + f"\n\n... (truncated, {len(resp.text)} chars total)"

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Fetched content from {url} ({len(text):,} chars)",
        "result": {
            "url": url,
            "content": text,
            "content_length": len(text),
        },
        "metadata": _meta(
            bytes_affected=len(resp.content),
            duration_ms=elapsed,
        ),
    }


# ---------------------------------------------------------------------------
# extract_data — fetch a URL and use LLM to extract specific information
# ---------------------------------------------------------------------------

def _extract_data(params: dict, context: dict) -> dict:
    """Fetch a URL and use the LLM to extract specific data from it."""
    t0 = time.monotonic()
    url = params.get("url", "").strip()
    description = params.get("description", "").strip()

    # Also accept data passed directly (from a previous subtask's result)
    raw_content = params.get("content")
    direct_content = ""

    # Handle search results passed as a list of dicts (from search_web)
    if isinstance(raw_content, list):
        # Extract URLs and snippets from search results
        parts = []
        first_url = None
        for item in raw_content:
            if isinstance(item, dict):
                if not first_url and item.get("url"):
                    first_url = item["url"]
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                item_url = item.get("url", "")
                if title or snippet:
                    parts.append(f"{title}\n{snippet}\n{item_url}")
        if parts:
            direct_content = "\n\n".join(parts)
        # If we have a first URL from results, use it for deeper extraction
        if first_url and not url:
            url = first_url
    elif isinstance(raw_content, str):
        direct_content = raw_content.strip()

    if not url and not direct_content:
        return _error("MISSING_URL", "I need a URL or content to extract data from")

    if not description:
        return _error("MISSING_DESCRIPTION", "I need a description of what data to extract")

    if context.get("dry_run"):
        source = url or "provided content"
        return {
            "status": "success",
            "action_performed": f"Would extract '{description}' from {source}",
            "result": {"preview": f"Extract: {description}"},
            "metadata": _meta(),
        }

    llm_client = context.get("llm_client")
    if llm_client is None:
        return _error(
            "NO_LLM_CLIENT",
            "Data extraction requires the LLM — no API client available",
        )

    # Get the page content — combine sources when available
    page_text = ""

    # Start with search snippets if we have them
    if direct_content:
        page_text = direct_content

    # Supplement with fetched page content if a URL is available
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            resp = requests.get(
                url,
                headers=_get_headers(),
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
            fetched = _clean_text(resp.text)
            if page_text:
                page_text = (
                    "--- SEARCH RESULTS ---\n"
                    + page_text
                    + "\n\n--- FULL PAGE CONTENT ---\n"
                    + fetched
                )
            else:
                page_text = fetched
        except requests.RequestException:
            # If fetch fails but we have search snippets, continue with those
            if not page_text:
                return _error("FETCH_FAILED", "Could not fetch that page and no other content available")

    if not page_text:
        return _error("NO_CONTENT", "No URL or content provided for extraction")

    # Truncate for LLM context
    if len(page_text) > _MAX_EXTRACT_CHARS:
        page_text = page_text[:_MAX_EXTRACT_CHARS] + "\n\n... (content truncated)"

    # Ask the LLM to extract the requested data
    extraction_prompt = f"""\
Extract the following information from the web page content below.

What to extract: {description}

Return ONLY the extracted data as plain text. Be concise and factual.
If you cannot find the requested information, say "Not found" and explain briefly.
Do not add commentary or formatting beyond what is needed.

--- PAGE CONTENT ---
{page_text}
--- END ---"""

    try:
        response = llm_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": extraction_prompt}],
        )
        extracted = response.content[0].text.strip()
    except Exception:
        return _error("LLM_ERROR", "Something went wrong while analyzing the page content")

    elapsed = int((time.monotonic() - t0) * 1000)
    source = url or "provided content"
    return {
        "status": "success",
        "action_performed": f"Extracted '{description}' from {source}",
        "result": {
            "source": source,
            "description": description,
            "extracted_data": extracted,
        },
        "metadata": _meta(duration_ms=elapsed),
    }


# ---------------------------------------------------------------------------
# Action registry and entry point
# ---------------------------------------------------------------------------

_ACTIONS = {
    "search_web": _search_web,
    "fetch_page": _fetch_page,
    "extract_data": _extract_data,
}


def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return _error("UNKNOWN_ACTION", f"I don't know how to do '{action}'")

    try:
        return handler(params, context)
    except Exception:
        return _error("AGENT_CRASH", "Something went wrong running that operation")
