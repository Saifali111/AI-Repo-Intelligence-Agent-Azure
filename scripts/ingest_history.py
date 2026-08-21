"""
Step 2: Seed historical GitHub Issues and PRs into Azure AI Search.

Run:
    python3 -m scripts.ingest_history

What it does:
  - Paginates GitHub REST API for all issues (open + closed)
  - Uploads batches to devpulse-issues-index
  - Paginates GitHub PRs and uploads to devpulse-prs-index
  - Seeds devpulse-briefings-history with a starter briefing document
"""

import json
import time
import requests
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    GITHUB_TOKEN, DEFAULT_REPO,
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY,
    AZURE_SEARCH_ISSUES_INDEX, AZURE_SEARCH_HISTORY_INDEX,
    AZURE_SEARCH_PRS_INDEX,
)

HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
BATCH_SIZE = 50  # Azure AI Search upload batch limit


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
    """Converts raw GitHub API issue to search index document."""
    labels = ",".join([l.get("name", "") for l in issue.get("labels", [])])
    body = issue.get("body") or ""
    title = issue.get("title", "")
    # Combined content field for full-text search
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

    # Upload in batches
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        result = client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        print(f"  [Issues] Uploaded batch {i // BATCH_SIZE + 1}: {succeeded}/{len(batch)} succeeded.")

    print(f"  ✅ Issues ingestion complete. Total: {len(docs)} documents.")


# ─────────────────────────────────────────────────────────
# Ingest PRs
# ─────────────────────────────────────────────────────────

def fetch_github_prs(repo: str, max_pages: int = 5) -> list[dict]:
    """Paginates GitHub PRs API (open + closed)."""
    all_prs = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{repo}/pulls"
        params = {"state": "all", "per_page": 100, "page": page}
        resp = requests.get(url, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"  [PRs] HTTP {resp.status_code} on page {page}. Stopping.")
            break
        data = resp.json()
        if not data:
            break
        all_prs.extend(data)
        print(f"  [PRs] Page {page}: fetched {len(data)} PRs (total: {len(all_prs)})")
        time.sleep(0.5)
    return all_prs


def shape_pr_document(pr: dict) -> dict:
    """Converts raw GitHub PR to search index document."""
    body = pr.get("body") or ""
    title = pr.get("title", "")
    content = f"{title}\n\n{body[:2000]}"
    changed_files_str = json.dumps(pr.get("changed_files", []))
    return {
        "id": str(pr["id"]),
        "pr_number": pr.get("number", 0),
        "title": title,
        "body": body[:3000],
        "content": content,
        "state": pr.get("state", ""),
        "author": pr.get("user", {}).get("login", ""),
        "merged": pr.get("merged_at") is not None,
        "created_at": pr.get("created_at", ""),
        "merged_at": pr.get("merged_at") or "",
        "changed_files": changed_files_str,
    }


def ingest_prs(repo: str):
    print(f"\n📥 [PRs] Starting ingestion for repo: {repo}")
    prs = fetch_github_prs(repo)
    if not prs:
        print("  No PRs fetched.")
        return

    client = get_search_client(AZURE_SEARCH_PRS_INDEX)
    docs = [shape_pr_document(p) for p in prs]

    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        result = client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        print(f"  [PRs] Uploaded batch {i // BATCH_SIZE + 1}: {succeeded}/{len(batch)} succeeded.")

    print(f"  ✅ PRs ingestion complete. Total: {len(docs)} documents.")


# ─────────────────────────────────────────────────────────
# Seed Briefings History (starter docs)
# ─────────────────────────────────────────────────────────

STARTER_BRIEFINGS = [
    {
        "id": "briefing-001",
        "title": "App Router Focus/Blur Bug — Recurring Pattern",
        "content": (
            "Issue #81204 was a focus/blur regression in the Next.js App Router introduced in v13.4. "
            "Root cause: handleFocusBlur in app-router.tsx was not properly checking event.target before "
            "invoking router state transitions. Fixed by adding a null-guard on event.target (PR #81890). "
            "This same pattern resurfaced in Issue #96050 — check router.ts scroll/focus handlers first."
        ),
        "date": "2024-01-15",
        "issue_refs": "#81204,#96050",
        "author": "devpulse-system",
    },
    {
        "id": "briefing-002",
        "title": "Middleware Auth Token Expiry — Known Issue",
        "content": (
            "Issue #88312 documented a recurring problem where middleware JWT validation silently fails "
            "on token expiry without returning a 401, causing downstream components to receive undefined user. "
            "Resolution: add explicit token expiry check in middleware.ts before calling next(). Resolved in v14.1."
        ),
        "date": "2024-03-20",
        "issue_refs": "#88312",
        "author": "devpulse-system",
    },
]


def ingest_briefings():
    print(f"\n📥 [Briefings] Seeding starter briefings history...")
    client = get_search_client(AZURE_SEARCH_HISTORY_INDEX)
    result = client.upload_documents(documents=STARTER_BRIEFINGS)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"  ✅ Briefings seeded: {succeeded}/{len(STARTER_BRIEFINGS)} documents.")


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
    # NOTE: PR ingestion skipped — Free tier allows max 3 indexes.
    # PR data is fetched live via fetch_live_pr_details() GitHub API tool.
    ingest_briefings()

    print("\n=== Ingestion Complete ===")
    print("Next step: python3 -m scripts.repo_indexer  (to index the codebase)")


if __name__ == "__main__":
    main()
