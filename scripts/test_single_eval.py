"""
Smart PR Evaluation with Foundry LLM-as-a-Judge:
- Evaluates any specific PR: `python3 -m scripts.test_single_eval <PR_NUMBER>`
- Or auto-picks the latest merged PR: `python3 -m scripts.test_single_eval`
"""
import sys
import re
import json
import requests

from config.settings import GITHUB_TOKEN, DEFAULT_REPO
from config.azure_clients import get_agent_openai_client
from agents.agent_graph import run_devpulse_pipeline

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

SOURCE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".py")
JUDGE_AGENT_REFERENCE = {"name": "judge-agent", "type": "agent_reference"}


def fetch_latest_merged_pr():
    """Auto-discovers the latest merged TypeScript/JavaScript code fix from GitHub."""
    print(f"[Eval] Auto-discovering latest merged code fixes in '{DEFAULT_REPO}'...")
    url = f"https://api.github.com/repos/{DEFAULT_REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=30"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        raise RuntimeError(f"GitHub API Error: {res.text[:200]}")

    for pr in res.json():
        if not pr.get("merged_at"):
            continue
        title = pr.get("title", "").lower()
        # Skip docs, chores, and build script tweaks
        if title.startswith(("docs", "chore", "ci", "build", "release")):
            continue

        case = fetch_target_pr(pr["number"])
        if case["ground_truth_files"]:
            return case

    raise RuntimeError("No merged code fixes found.")



def fetch_target_pr(pr_number: int):
    """Fetches details, files, and diffs for a specific PR."""
    print(f"[Eval] Fetching PR #{pr_number} from '{DEFAULT_REPO}'...")
    url = f"https://api.github.com/repos/{DEFAULT_REPO}/pulls/{pr_number}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        raise RuntimeError(f"GitHub API Error: Could not find PR #{pr_number} (HTTP {res.status_code})")

    pr = res.json()
    body = (pr.get("body") or "") + " " + (pr.get("title") or "")
    
    match = re.search(r"(?:fix|fixes|close|closes|resolve|resolves)\s+(?:https?://github\.com/[^/]+/[^/]+/issues/|#)(\d+)", body, re.IGNORECASE)
    linked_issue = int(match.group(1)) if match else None

    files_url = pr.get("url") + "/files"
    files_res = requests.get(files_url, headers=HEADERS)
    
    changed_files = []
    patches = []
    if files_res.status_code == 200:
        for f in files_res.json():
            filename = f.get("filename", "")
            if any(filename.endswith(ext) for ext in SOURCE_EXTS) or "packages/" in filename:
                changed_files.append(filename)
                patch = f.get("patch", "")
                if patch:
                    patches.append(f"--- File: {filename} ---\n{patch[:600]}")

    return {
        "pr_number": pr["number"],
        "pr_title": pr["title"],
        "pr_body": (pr.get("body") or "")[:800],
        "linked_issue": linked_issue,
        "is_merged": pr.get("merged", False),
        "ground_truth_files": changed_files,
        "ground_truth_patch": "\n\n".join(patches[:4]),
    }


def run_foundry_judge_agent(case: dict, agent_output: str) -> dict:
    """Invokes 'judge-agent' in Microsoft Foundry via Responses API to score DevPulse."""
    print("[Foundry-Judge] Invoking 'judge-agent' in Azure AI Foundry...")
    client = get_agent_openai_client()
    if not client:
        return {"error": "Foundry agent client not configured."}

    eval_payload = f"""
[1] THE GITHUB PROBLEM / ISSUE
Problem: {case['pr_title']}
Description: {case['pr_body']}
Linked Issue: #{case['linked_issue'] if case['linked_issue'] else 'Standalone PR'}

[2] GROUND TRUTH APPROVED FIX (PR #{case['pr_number']})
PR Title: {case['pr_title']}
Files Modified by Human Maintainers: {json.dumps(case['ground_truth_files'])}

Actual Merged Code Diff:
{case['ground_truth_patch']}

[3] DEVPULSE AGENT GENERATED DIAGNOSIS & CODE FIX
{agent_output}

Compare the AI diagnosis and proposed code fix against the human maintainers' approved fix. Output JSON evaluation.
"""

    try:
        response = client.responses.create(
            extra_body={"agent_reference": JUDGE_AGENT_REFERENCE},
            input=[{"role": "user", "content": eval_payload}]
        )
        raw_text = response.output_text or ""
        if "```" in raw_text:
            raw_text = re.sub(r"```(?:json)?", "", raw_text).strip("` \n")
        return json.loads(raw_text)
    except Exception as e:
        return {"error": f"Judge agent failed: {e}", "raw_response": raw_text if 'raw_text' in locals() else ""}


def main():
    if len(sys.argv) > 1:
        target_pr_num = int(sys.argv[1])
        case = fetch_target_pr(target_pr_num)
    else:
        case = fetch_latest_merged_pr()

    gt_files = case["ground_truth_files"]

    print(f"\n🎯 Target PR Selected:")
    print(f"   • PR #{case['pr_number']}: '{case['pr_title']}'")
    print(f"   • Linked Issue: #{case['linked_issue'] if case['linked_issue'] else 'Direct PR'}")
    print(f"   • Files Modified in PR: {gt_files}")
    print("\n" + "=" * 60 + "\n")

    # Query DevPulse
    query = f"Please tell me about issue #{case['linked_issue']}?" if case['linked_issue'] else f"Please diagnose: {case['pr_title']}"
    print(f"[DevPulse] Running agent pipeline for query: '{query}'...")
    pipeline_result = run_devpulse_pipeline(query)
    agent_response = pipeline_result.get("response", "")

    print("\n" + "=" * 60)
    print("🤖 DEVPULSE GENERATED DIAGNOSIS:")
    print("=" * 60)
    print(agent_response)
    print("=" * 60 + "\n")

    # Deterministic File Check
    hits = [f for f in gt_files if f in agent_response or f.split("/")[-1] in agent_response]
    print(f"📁 Deterministic File Check: {'✅ Hit (' + str(hits) + ')' if hits else '⚠️ Miss'}")

    # Foundry Judge Agent Evaluation
    judge_result = run_foundry_judge_agent(case, agent_response)

    print("\n" + "=" * 60)
    print("⚖️ FOUNDRY 'judge-agent' EVALUATION:")
    print("=" * 60)
    if "error" in judge_result and not judge_result.get("overall_verdict"):
        print(f"Error: {judge_result}")
    else:
        print(f"   • Overall Verdict:           {judge_result.get('overall_verdict')}")
        print(f"   • Root Cause Alignment:      {judge_result.get('root_cause_score')}/5")
        print(f"   • Solution Correctness:      {judge_result.get('solution_correctness_score')}/5")
        print(f"   • File Localization Score:   {judge_result.get('file_localization_score')}/5")
        print(f"\n   📝 Judge Summary:\n   {judge_result.get('judge_summary')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
