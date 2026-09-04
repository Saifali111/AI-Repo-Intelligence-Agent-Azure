"""
GitHub Issue Ingestion Pipeline.
Fetches repository issues from GitHub, generates dense vector embeddings, and uploads them to Azure AI Search.
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
BATCH_SIZE = 50


def get_search_client(index_name: str) -> SearchClient:
    """Initializes and returns the SearchClient for document uploads."""
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def fetch_github_issues(repo: str, max_pages: int = 3) -> list[dict]:
    """Fetches paginated issues from the GitHub REST API, excluding pull requests."""
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
        issues_only = [i for i in data if "pull_request" not in i]
        all_issues.extend(issues_only)
        print(f"  [Issues] Page {page}: fetched {len(issues_only)} issues (total so far: {len(all_issues)})")
        if len(data) < 100:
            print(f"  [Issues] Last page reached at page {page}.")
            break
        time.sleep(0.8)
    return all_issues


def shape_issue_document(issue: dict) -> dict:
    """Formats a raw GitHub issue dictionary into the search index document structure."""
    labels = ",".join([l.get("name", "") for l in issue.get("labels", [])])
    body = issue.get("body") or ""
    title = issue.get("title", "")
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
        "resolution_summary": "",
    }


def ingest_issues(repo: str):
    """Fetches, embeds, and uploads issues in batches to Azure AI Search."""
    print(f"\n📥 [Issues] Starting ingestion for repo: {repo}")
    issues = fetch_github_issues(repo)
    if not issues:
        print("  No issues fetched. Check GITHUB_TOKEN and repo name.")
        return

    client = get_search_client(AZURE_SEARCH_ISSUES_INDEX)
    docs = [shape_issue_document(i) for i in issues]

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


def main():
    """Runs the issue ingestion workflow for the default repository."""
    print("=== DevPulse: Historical Data Ingestion ===")
    print(f"Target repo: {DEFAULT_REPO}\n")

    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY is not set in .env. Aborting.")
        return

    ingest_issues(DEFAULT_REPO)
    print("\n=== Ingestion Complete ===")


if __name__ == "__main__":
    main()