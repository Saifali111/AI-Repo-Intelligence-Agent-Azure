"""
DevPulse: Batch Ground-Truth Evaluation Benchmark
1. Auto-discovers N recent merged code PRs from GitHub (skipping docs/chores).
2. Runs DevPulse on each issue/problem.
3. Invokes Foundry's 'judge-agent' to score each diagnosis against real maintainer patches.
4. Computes aggregate metrics: Root Cause Alignment, Solution Score, and File Hit Rate.
5. Outputs a senior-level Markdown benchmark report table!

Usage:
    python3 -m scripts.run_eval_benchmark --count 5
"""
import sys
import re
import json
import time
import argparse
import requests

from config.settings import GITHUB_TOKEN, DEFAULT_REPO
from config.azure_clients import get_agent_openai_client
from agents.agent_graph import run_devpulse_pipeline

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

SOURCE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".py")
JUDGE_AGENT_REFERENCE = {"name": "judge-agent", "type": "agent_reference"}


def discover_benchmark_prs(repo: str, target_count: int = 5, max_pages: int = 10) -> list[dict]:
    """Paginates GitHub and collects real merged PRs containing TypeScript/JavaScript code fixes."""
    print(f"\n🔍 [Discovery] Finding {target_count} merged code PRs from '{repo}'...")
    collected = []

    for page in range(1, max_pages + 1):
        if len(collected) >= target_count:
            break

        url = f"https://api.github.com/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=30&page={page}"
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            print(f"  ⚠️ GitHub API HTTP {res.status_code}. Stopping discovery.")
            break

        prs = res.json()
        if not prs or not isinstance(prs, list):
            break

        for pr in prs:
            if len(collected) >= target_count:
                break
            if not pr.get("merged_at"):
                continue

            title = pr.get("title", "")
            title_lower = title.lower()
            # Skip documentation, chores, and releases
            if title_lower.startswith(("docs", "chore", "ci", "build", "release", "repo:", "deps", "fix(deps)", "feat(deps)")):
                continue

            body = (pr.get("body") or "") + " " + title
            match = re.search(r"(?:fix|fixes|close|closes|resolve|resolves)\s+(?:https?://github\.com/[^/]+/[^/]+/issues/|#)(\d+)", body, re.IGNORECASE)
            linked_issue = int(match.group(1)) if match else None

            # Fetch modified files
            files_res = requests.get(pr.get("url") + "/files", headers=HEADERS)
            if files_res.status_code != 200:
                continue

            changed_files = []
            patches = []
            for f in files_res.json():
                filename = f.get("filename", "")
                if any(filename.endswith(ext) for ext in SOURCE_EXTS) or "packages/" in filename:
                    changed_files.append(filename)
                    patch = f.get("patch", "")
                    if patch:
                        patches.append(f"--- File: {filename} ---\n{patch[:500]}")

            if changed_files and patches:
                print(f"  ✅ [Case {len(collected)+1}/{target_count}] PR #{pr['number']}: '{title[:50]}...' ({len(changed_files)} files)")
                collected.append({
                    "pr_number": pr["number"],
                    "pr_title": title,
                    "pr_body": (pr.get("body") or "")[:600],
                    "linked_issue": linked_issue,
                    "ground_truth_files": changed_files,
                    "ground_truth_patch": "\n\n".join(patches[:3]),
                })
                time.sleep(0.5)

    return collected


def run_foundry_judge_agent(case: dict, agent_output: str) -> dict:
    """Invokes Microsoft Foundry's 'judge-agent' via Responses API."""
    client = get_agent_openai_client()
    if not client:
        return {"error": "Foundry agent client not configured."}

    eval_payload = f"""
[1] THE GITHUB PROBLEM / ISSUE
Problem: {case['pr_title']}
Description: {case['pr_body']}
Linked Issue: #{case['linked_issue'] if case['linked_issue'] else 'Direct PR'}

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
        return {"error": str(e), "root_cause_score": 1, "solution_correctness_score": 1, "file_localization_score": 1, "overall_verdict": "ERROR"}


def main():
    parser = argparse.ArgumentParser(description="Run DevPulse LLM-as-a-Judge Evaluation Benchmark")
    parser.add_argument("--count", type=int, default=5, help="Number of PR test cases to evaluate (default: 5)")
    args = parser.parse_args()

    print(f"============================================================")
    print(f"📊 DevPulse: Multi-Case Ground Truth Benchmark ({args.count} Cases)")
    print(f"   Target Repository: {DEFAULT_REPO}")
    print(f"   Evaluation Judge:  Foundry 'judge-agent'")
    print(f"============================================================")

    # 1. Discover PRs
    cases = discover_benchmark_prs(DEFAULT_REPO, target_count=args.count)
    if not cases:
        print("❌ No benchmark PRs found.")
        return

    results = []

    # 2. Run Benchmark Loop
    for i, case in enumerate(cases, 1):
        pr_num = case["pr_number"]
        gt_files = case["ground_truth_files"]
        query = f"Please tell me about issue #{case['linked_issue']}?" if case['linked_issue'] else f"Please diagnose: {case['pr_title']}"

        print(f"\n[{i}/{len(cases)}] 🚀 Testing PR #{pr_num}: '{case['pr_title'][:60]}'")
        print(f"   Query: '{query}'")

        # Run DevPulse
        t0 = time.time()
        pipeline_res = run_devpulse_pipeline(query)
        duration = round(time.time() - t0, 1)
        agent_resp = pipeline_res.get("response", "")

        # Deterministic file check
        hits = [f for f in gt_files if f in agent_resp or f.split("/")[-1] in agent_resp]
        file_hit = len(hits) > 0

        # Invoke Foundry Judge
        print(f"   ⚖️ Invoking 'judge-agent' in Microsoft Foundry...")
        judge_res = run_foundry_judge_agent(case, agent_resp)

        rc_score = judge_res.get("root_cause_score", 1)
        sol_score = judge_res.get("solution_correctness_score", 1)
        loc_score = judge_res.get("file_localization_score", 1)
        verdict = judge_res.get("overall_verdict", "FAIL")

        print(f"   📊 Score: RootCause={rc_score}/5 | Solution={sol_score}/5 | FileLoc={loc_score}/5 | FileHit={'✅' if file_hit else '❌'} | ({duration}s)")

        results.append({
            "pr_number": pr_num,
            "title": case["pr_title"][:40],
            "duration": duration,
            "root_cause_score": rc_score,
            "solution_score": sol_score,
            "localization_score": loc_score,
            "file_hit": file_hit,
            "verdict": verdict,
            "summary": judge_res.get("judge_summary", "")
        })

    # 3. Aggregate Statistics
    total = len(results)
    avg_rc = sum(r["root_cause_score"] for r in results) / total
    avg_sol = sum(r["solution_score"] for r in results) / total
    avg_loc = sum(r["localization_score"] for r in results) / total
    hit_rate = (sum(1 for r in results if r["file_hit"]) / total) * 100

    # 4. Render Markdown Benchmark Table
    print("\n" + "=" * 80)
    print("🏆 DEVPULSE BENCHMARK EVALUATION SUMMARY")
    print("=" * 80)
    print(f"| PR # | Title | Latency | Root Cause | Solution | File Loc | File Hit | Verdict |")
    print(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        hit_icon = "✅ Hit" if r["file_hit"] else "❌ Miss"
        print(f"| #{r['pr_number']} | {r['title']} | {r['duration']}s | {r['root_cause_score']}/5 | {r['solution_score']}/5 | {r['localization_score']}/5 | {hit_icon} | {r['verdict']} |")

    print("\n" + "-" * 80)
    print(f"📈 AGGREGATE PERFORMANCE METRICS (N={total} Cases):")
    print(f"   • Mean Root Cause Alignment:    {avg_rc:.2f} / 5.0  ({(avg_rc/5)*100:.1f}%)")
    print(f"   • Mean Solution Correctness:    {avg_sol:.2f} / 5.0  ({(avg_sol/5)*100:.1f}%)")
    print(f"   • Mean File Localization:       {avg_loc:.2f} / 5.0")
    print(f"   • Deterministic File Hit Rate:  {hit_rate:.1f}%")
    print("=" * 80 + "\n")

    # Save to JSON
    with open("benchmark_results.json", "w") as f:
        json.dump({"metrics": {"avg_root_cause": avg_rc, "avg_solution": avg_sol, "hit_rate": hit_rate}, "cases": results}, f, indent=2)
    print("💾 Benchmark results saved to 'benchmark_results.json'!\n")


if __name__ == "__main__":
    main()
