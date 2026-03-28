"""
IntentOS Phase 2 — Integration Tests

Tests browser_agent and document_agent working together through direct
agent calls (simulating the kernel's subtask execution pipeline).

Test 1: Web search for gold price in UAE dirhams
Test 2: Search + create goldrate.docx
Test 3: Search + create iphone_prices.docx
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

import anthropic

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _setup():
    """Create API client and execution context."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    home = os.path.expanduser("~")
    workspace = os.path.join(home, ".intentos", "workspace")
    output_dir = os.path.join(workspace, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    context = {
        "user": os.getenv("USER", "test"),
        "workspace": workspace,
        "granted_paths": [
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop"),
            workspace,
        ],
        "task_id": f"test-phase2-{int(time.time())}",
        "dry_run": False,
        "llm_client": client,
    }

    return client, context, output_dir


# ---------------------------------------------------------------------------
# Test 1: Web search only
# ---------------------------------------------------------------------------

def test_1_web_search(context: dict) -> bool:
    """Search the web for current gold price in UAE dirhams."""
    print()
    print("=" * 60)
    print("  TEST 1: Web search for UAE gold price")
    print("=" * 60)
    print()

    from capabilities.browser_agent.agent import run as browser_run

    t0 = time.monotonic()

    # Step 1: Search
    print("  [1] browser_agent.search_web...")
    result = browser_run({
        "action": "search_web",
        "params": {"query": "current gold price in UAE dirhams per gram today", "max_results": 5},
        "context": context,
    })

    if result["status"] != "success":
        print(f"  FAIL: search_web — {result.get('error', {}).get('message', '?')}")
        return False

    search_results = result["result"]
    print(f"      Found {len(search_results)} result(s)")

    # Step 2: Extract data from search results
    print("  [2] browser_agent.extract_data...")
    extract_result = browser_run({
        "action": "extract_data",
        "params": {
            "content": search_results,
            "description": "Current gold price in UAE dirhams (AED) per gram, including 24K, 22K, 21K rates if available",
        },
        "context": context,
    })

    if extract_result["status"] != "success":
        print(f"  FAIL: extract_data — {extract_result.get('error', {}).get('message', '?')}")
        return False

    extracted = extract_result["result"]["extracted_data"]
    elapsed = int((time.monotonic() - t0) * 1000)

    print()
    print("  --- Extracted Gold Price ---")
    for line in extracted.strip().split("\n"):
        print(f"    {line}")
    print("  ---")
    print()

    # Validate
    checks = {
        "search returned results": len(search_results) > 0,
        "extract returned data": len(extracted) > 10,
        "mentions gold or AED": "gold" in extracted.lower() or "aed" in extracted.lower() or "dirham" in extracted.lower(),
    }

    all_pass = True
    for label, passed in checks.items():
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label}")
        if not passed:
            all_pass = False

    print(f"  Time: {elapsed}ms")
    return all_pass


# ---------------------------------------------------------------------------
# Test 2: Search + create goldrate.docx
# ---------------------------------------------------------------------------

def test_2_gold_document(context: dict, output_dir: str) -> bool:
    """Search for gold price, create goldrate.docx."""
    print()
    print("=" * 60)
    print("  TEST 2: Create goldrate.docx with UAE gold price")
    print("=" * 60)
    print()

    from capabilities.browser_agent.agent import run as browser_run
    from capabilities.document_agent.agent import run as document_run

    t0 = time.monotonic()
    today = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Search
    print("  [1] browser_agent.search_web...")
    search = browser_run({
        "action": "search_web",
        "params": {"query": "gold rate in UAE dirhams today per gram", "max_results": 5},
        "context": context,
    })

    if search["status"] != "success":
        print(f"  FAIL: search_web — {search.get('error', {}).get('message', '?')}")
        return False

    print(f"      {len(search['result'])} result(s)")

    # Step 2: Extract price
    print("  [2] browser_agent.extract_data...")
    extract = browser_run({
        "action": "extract_data",
        "params": {
            "content": search["result"],
            "description": (
                "The current gold price in UAE dirhams (AED) per gram. "
                "Include 24K, 22K, and 21K rates. Note the date if mentioned."
            ),
        },
        "context": context,
    })

    if extract["status"] != "success":
        print(f"  FAIL: extract_data — {extract.get('error', {}).get('message', '?')}")
        return False

    gold_data = extract["result"]["extracted_data"]
    print(f"      Extracted {len(gold_data)} chars")

    # Step 3: Create document
    print("  [3] document_agent.create_document...")
    doc_content = f"Gold Rate in UAE (AED) — {today}\n\n{gold_data}\n\nSource: DuckDuckGo web search"
    doc = document_run({
        "action": "create_document",
        "params": {
            "filename": "goldrate",
            "content": doc_content,
            "title": f"Gold Rate in UAE — {today}",
        },
        "context": context,
    })

    if doc["status"] != "success":
        print(f"  FAIL: create_document — {doc.get('error', {}).get('message', '?')}")
        return False

    output_path = doc["result"]["path"]
    elapsed = int((time.monotonic() - t0) * 1000)

    print(f"      Created: {output_path}")
    print(f"      Size: {doc['result']['size_bytes']:,} bytes")
    print()

    # Validate
    expected_path = os.path.join(output_dir, "goldrate.docx")
    checks = {
        "file exists": os.path.exists(output_path),
        "correct path": output_path == expected_path,
        "is .docx": output_path.endswith(".docx"),
        "non-empty": doc["result"]["size_bytes"] > 0,
        "gold data extracted": len(gold_data) > 10,
    }

    all_pass = True
    for label, passed in checks.items():
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label}")
        if not passed:
            all_pass = False

    print(f"  Time: {elapsed}ms")
    print(f"  Output: {output_path}")
    return all_pass


# ---------------------------------------------------------------------------
# Test 3: Multi-source search + iphone_prices.docx
# ---------------------------------------------------------------------------

def test_3_iphone_document(context: dict, output_dir: str) -> bool:
    """Search for iPhone 16 prices, create iphone_prices.docx."""
    print()
    print("=" * 60)
    print("  TEST 3: Create iphone_prices.docx with iPhone 16 prices")
    print("=" * 60)
    print()

    from capabilities.browser_agent.agent import run as browser_run
    from capabilities.document_agent.agent import run as document_run

    t0 = time.monotonic()
    today = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Search
    print("  [1] browser_agent.search_web...")
    search = browser_run({
        "action": "search_web",
        "params": {"query": "cheapest iPhone 16 price online 2024 2025", "max_results": 5},
        "context": context,
    })

    if search["status"] != "success":
        print(f"  FAIL: search_web — {search.get('error', {}).get('message', '?')}")
        return False

    results = search["result"]
    print(f"      {len(results)} result(s)")
    for r in results[:3]:
        print(f"      - {r.get('title', '?')[:60]}")

    # Step 2: Extract prices
    print("  [2] browser_agent.extract_data...")
    extract = browser_run({
        "action": "extract_data",
        "params": {
            "content": results,
            "description": (
                "iPhone 16 prices from different sources. "
                "List the price, model variant, and store/source for each result. "
                "Format as a comparison list."
            ),
        },
        "context": context,
    })

    if extract["status"] != "success":
        print(f"  FAIL: extract_data — {extract.get('error', {}).get('message', '?')}")
        return False

    price_data = extract["result"]["extracted_data"]
    print(f"      Extracted {len(price_data)} chars")

    # Step 3: Create document
    print("  [3] document_agent.create_document...")
    doc_content = (
        f"iPhone 16 Price Comparison — {today}\n\n"
        f"{price_data}\n\n"
        f"Source: DuckDuckGo web search\n"
        f"Note: Prices may vary. Check retailer websites for current pricing."
    )
    doc = document_run({
        "action": "create_document",
        "params": {
            "filename": "iphone_prices",
            "content": doc_content,
            "title": f"iPhone 16 Price Comparison — {today}",
        },
        "context": context,
    })

    if doc["status"] != "success":
        print(f"  FAIL: create_document — {doc.get('error', {}).get('message', '?')}")
        return False

    output_path = doc["result"]["path"]
    elapsed = int((time.monotonic() - t0) * 1000)

    print(f"      Created: {output_path}")
    print(f"      Size: {doc['result']['size_bytes']:,} bytes")
    print()

    # Validate
    expected_path = os.path.join(output_dir, "iphone_prices.docx")
    checks = {
        "file exists": os.path.exists(output_path),
        "correct path": output_path == expected_path,
        "is .docx": output_path.endswith(".docx"),
        "non-empty": doc["result"]["size_bytes"] > 0,
        "price data extracted": len(price_data) > 10,
    }

    all_pass = True
    for label, passed in checks.items():
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label}")
        if not passed:
            all_pass = False

    print(f"  Time: {elapsed}ms")
    print(f"  Output: {output_path}")
    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 60)
    print("  IntentOS Phase 2 — Integration Tests")
    print("=" * 60)

    client, context, output_dir = _setup()

    results = {}

    results["Test 1"] = test_1_web_search(context)
    results["Test 2"] = test_2_gold_document(context, output_dir)
    results["Test 3"] = test_3_iphone_document(context, output_dir)

    # Final report
    print()
    print()
    print("=" * 60)
    print("  PHASE 2 TEST RESULTS")
    print("=" * 60)
    for name, passed in results.items():
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
    print("=" * 60)

    all_passed = all(results.values())
    if all_passed:
        print("  All tests passed.")
    else:
        failed = [name for name, p in results.items() if not p]
        print(f"  Failed: {', '.join(failed)}")

    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
