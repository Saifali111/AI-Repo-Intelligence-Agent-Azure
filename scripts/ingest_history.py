"""
Step 2: Seed historical GitHub Issues into Azure AI Search, with embeddings.

Run:
    python3 -m scripts.ingest_history

What it does:
  - Paginates GitHub REST API for all issues (open + closed)
  - Embeds each issue's title+body via Azure OpenAI (text-embedding-3-large)
  - Uploads batches (text + vector) to devpulse-issues-index
"""

import time
import requests
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    GITHUB_TOKEN, DEFAULT_REPO,
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY,
    AZURE_SEARCH_ISSUES_INDEX,
)
from tools.search_tools import get_embeddings_batch

HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
BATCH_SIZE = 50  # Azure AI Search upload batch limit; also our embedding batch size


def get_search_client(index_name: str) -> SearchClient:
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


# ─────────────────────────────────────────────────────────
# Ingest Issues
# ─────────────────────────────────────────────────────────

def fetch_github_issues(repo: str, max_pages: int = 50) -> list[dict]:
    """Paginates GitHub issues API (open + closed), returns raw list."""
    all_issues = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {"state": "all", "per_page": 100, "page": page}
        resp = requests.get(url, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"  [Issues] HTTP {resp.status_code} on page {page}. Stopping.")
            break
        data = resp.json()
        if not data:
            break
        # Exclude PRs — GitHub issues API returns both issues and PRs
        issues_only = [i for i in data if "pull_request" not in i]
        all_issues.extend(issues_only)
        print(f"  [Issues] Page {page}: fetched {len(issues_only)} issues (total so far: {len(all_issues)})")
        # If the page returned fewer than 100 items, we've hit the last page
        if len(data) < 100:
            print(f"  [Issues] Last page reached at page {page}.")
            break
        time.sleep(0.8)  # stay within GitHub's 5000 req/hr rate limit
    return all_issues


def shape_issue_document(issue: dict) -> dict:
    """Converts raw GitHub API issue to search index document (text fields only —
    content_vector is attached separately, per upload batch, in ingest_issues())."""
    labels = ",".join([l.get("name", "") for l in issue.get("labels", [])])
    body = issue.get("body") or ""
    title = issue.get("title", "")
    # Combined content field for full-text search AND the text we embed
    content = f"{title}\n\n{body[:2000]}"
    return {
        "id": str(issue["id"]),
        "issue_number": issue.get("number", 0),
        "title": title,
        "body": body[:3000],
        "content": content,
        "state": issue.get("state", ""),
        "author": issue.get("user", {}).get("login", ""),
        "labels": labels,
        "created_at": issue.get("created_at", ""),
        "closed_at": issue.get("closed_at") or "",
        "resolution_summary": "",  # Can be enriched later
    }


def ingest_issues(repo: str):
    print(f"\n📥 [Issues] Starting ingestion for repo: {repo}")
    issues = fetch_github_issues(repo)
    if not issues:
        print("  No issues fetched. Check GITHUB_TOKEN and repo name.")
        return

    client = get_search_client(AZURE_SEARCH_ISSUES_INDEX)
    docs = [shape_issue_document(i) for i in issues]

    # Upload in batches — embed each batch's `content` right before uploading,
    # so one embeddings API call covers up to BATCH_SIZE issues at once
    # instead of one call per issue.
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]

        texts = [d["content"] for d in batch]
        print(f"  [Issues] Embedding batch {i // BATCH_SIZE + 1} ({len(texts)} issues)...")
        vectors = get_embeddings_batch(texts)

        for doc, vector in zip(batch, vectors):
            doc["content_vector"] = vector

        result = client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        print(f"  [Issues] Uploaded batch {i // BATCH_SIZE + 1}: {succeeded}/{len(batch)} succeeded.")

    print(f"  ✅ Issues ingestion complete. Total: {len(docs)} documents.")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main():
    print("=== DevPulse: Historical Data Ingestion ===")
    print(f"Target repo: {DEFAULT_REPO}\n")

    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY is not set in .env. Aborting.")
        return

    ingest_issues(DEFAULT_REPO)
    # NOTE: PR ingestion removed — Free tier allows max 3 indexes, and PRs
    # are covered live via fetch_live_pr_details() instead.

    print("\n=== Ingestion Complete ===")
    print("Next step: python3 -m scripts.repo_indexer  (to index the codebase)")


if __name__ == "__main__":
    main()