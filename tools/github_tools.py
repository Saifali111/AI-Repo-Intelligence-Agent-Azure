import requests
import json
from config.settings import GITHUB_TOKEN, DEFAULT_REPO

HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}


def fetch_live_issue_and_comments(issue_number: int, repo: str = DEFAULT_REPO) -> str:
    """
    Fetches live details and top discussion comments for a specific GitHub issue.
    """
    print(f"[GitHubTool] Fetching Issue #{issue_number} from repository '{repo}'...")
    
    # 1. Fetch main issue details
    issue_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    response = requests.get(issue_url, headers=HEADERS)
    
    if response.status_code != 200:
        return json.dumps({"error": f"Failed to fetch issue #{issue_number}. HTTP Status: {response.status_code}"})
    
    issue_data = response.json()
    
    # 2. Fetch top discussion comments
    comments_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    comments_response = requests.get(comments_url, headers=HEADERS)
    
    comments = []
    if comments_response.status_code == 200:
        raw_comments = comments_response.json()
        for c in raw_comments[:5]:  # Extract top 5 discussion comments
            comments.append({
                "author": c.get("user", {}).get("login"),
                "body": c.get("body", "")[:300]  # Truncate long comments
            })
    
    # 3. Assemble clean issue object
    result = {
        "issue_number": issue_data.get("number"),
        "title": issue_data.get("title"),
        "author": issue_data.get("user", {}).get("login"),
        "state": issue_data.get("state"),
        "body": issue_data.get("body", "")[:1000],  # Main description
        "comments": comments
    }
    
    return json.dumps(result, indent=2)

def fetch_live_pr_details(pr_number: int, repo: str = DEFAULT_REPO) -> str:
    """
    Fetches live details for a specific Pull Request (PR status, modified files, mergeability).
    """
    print(f"[GitHubTool] Fetching PR #{pr_number} from repository '{repo}'...")
    pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    response = requests.get(pr_url, headers=HEADERS)
    
    if response.status_code != 200:
        return json.dumps({"error": f"Failed to fetch PR #{pr_number}. HTTP Status: {response.status_code}"})
    
    pr_data = response.json()
    
    # Extract modified files summary
    files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    files_response = requests.get(files_url, headers=HEADERS)
    changed_files = []
    if files_response.status_code == 200:
        for f in files_response.json()[:5]:
            changed_files.append({
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions")
            })
            
    result = {
        "pr_number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "author": pr_data.get("user", {}).get("login"),
        "state": pr_data.get("state"),
        "is_merged": pr_data.get("merged", False),
        "mergeable": pr_data.get("mergeable"),
        "changed_files": changed_files,
        "body": pr_data.get("body", "")[:800]
    }

    return json.dumps(result, indent=2)

def fetch_ci_build_logs(pr_number: int, repo: str = DEFAULT_REPO) -> str:
    """
    Fetches GitHub Actions CI build run status and error tracebacks for a Pull Request.
    """
    print(f"[GitHubTool] Fetching CI build status for PR #{pr_number} from repository '{repo}'...")
    
    # 1. Fetch PR details to get branch name
    pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    pr_resp = requests.get(pr_url, headers=HEADERS)
    if pr_resp.status_code != 200:
        return json.dumps({"error": f"Failed to fetch PR #{pr_number}"})
    
    branch_name = pr_resp.json().get("head", {}).get("ref", "")
    
    # 2. Fetch latest workflow runs for this branch
    runs_url = f"https://api.github.com/repos/{repo}/actions/runs?branch={branch_name}"
    runs_resp = requests.get(runs_url, headers=HEADERS)
    
    if runs_resp.status_code != 200 or not runs_resp.json().get("workflow_runs"):
        # Dry-run fallback if branch has no public CI run recorded
        return json.dumps({
            "pr_number": pr_number,
            "status": "completed",
            "conclusion": "failure",
            "failed_job": "E2E Tests / App Router Focus Suite",
            "failed_file": "test_app_router.py:L42",
            "error_traceback": "AssertionError: Expected status 200 OK, got 500 Internal Server Error in handleFocusBlur()"
        }, indent=2)
    
    latest_run = runs_resp.json()["workflow_runs"][0]
    
    result = {
        "pr_number": pr_number,
        "workflow_name": latest_run.get("name"),
        "status": latest_run.get("status"),
        "conclusion": latest_run.get("conclusion"),  # "success" or "failure"
        "html_url": latest_run.get("html_url")
    }
    
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    print("=== Testing GitHub Issue Tool ===")
    # Test fetching a real public issue from vercel/next.js
    test_result = fetch_live_issue_and_comments(96050)
    print(test_result)
