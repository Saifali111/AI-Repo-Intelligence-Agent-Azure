import json
import requests
from config.azure_clients import get_agent_openai_client
from config.settings import (
    AZURE_AI_AGENT_NAME,
    AZURE_CONTENT_SAFETY_ENDPOINT,
    AZURE_CONTENT_SAFETY_KEY,
)
from tools.github_tools import (
    fetch_live_issue_and_comments,
    fetch_live_pr_details,
    fetch_ci_build_logs
)
from tools.search_tools import search_past_history, search_codebase

TOOL_MAP = {
    "fetch_live_issue_and_comments": fetch_live_issue_and_comments,
    "fetch_live_pr_details":         fetch_live_pr_details,
    "fetch_ci_build_logs":           fetch_ci_build_logs,
    "search_past_history":           search_past_history,
    "search_codebase":               search_codebase,
}

AGENT_REFERENCE = {"name": AZURE_AI_AGENT_NAME, "type": "agent_reference"}


def screen_input_safety(text: str) -> bool:
    """
    Pre-screens user input via Azure AI Content Safety API.
    Returns True if input is safe, False if it should be blocked.
    Falls through (returns True) if Content Safety is not configured.
    """
    if not AZURE_CONTENT_SAFETY_ENDPOINT or not AZURE_CONTENT_SAFETY_KEY:
        print("[ContentSafety] Not configured — skipping pre-screen.")
        return True

    try:
        url = f"{AZURE_CONTENT_SAFETY_ENDPOINT.rstrip('/')}/contentsafety/text:analyze?api-version=2024-09-01"
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_CONTENT_SAFETY_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text[:10000],  # API max length
            "categories": ["Hate", "Violence", "SelfHarm", "Sexual"],
            "blocklistNames": [],
            "outputType": "FourSeverityLevels",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        resp.raise_for_status()
        result = resp.json()

        # Block if ANY category severity >= 2 (medium)
        for cat in result.get("categoriesAnalysis", []):
            if cat.get("severity", 0) >= 2:
                print(f"[ContentSafety] BLOCKED — category '{cat['category']}' severity {cat['severity']}.")
                return False

        print("[ContentSafety] Input passed safety check.")
        return True

    except Exception as e:
        print(f"[ContentSafety] Screen failed (non-blocking): {e}")
        return True  # Fail open — don't block on API errors


def run_maintainer_assistant(user_input: str, conversation_id: str = None) -> tuple[str, str]:
    """
    Executes the Maintainer Assistant Agent via the Foundry Agent Service (Responses API).
    Pre-screens input through Azure AI Content Safety before invoking the agent.
    Returns (final_text, conversation_id).
    """
    print(f"[AssistantAgent] Processing input: '{user_input}'...")

    # ── Step 0: Content Safety pre-screen ──────────────────────────────────
    if not screen_input_safety(user_input):
        return (
            "⚠️ Your query was flagged by the content safety filter and cannot be processed. "
            "Please rephrase your question.",
            conversation_id or "",
        )

    # ── Step 1: Get Foundry client ──────────────────────────────────────────
    client = get_agent_openai_client()
    if not client:
        raise RuntimeError(
            "[AssistantAgent Error] Foundry Agent client is not configured. "
            "Check AZURE_AI_PROJECT_ENDPOINT in your .env and ensure the agent "
            f"'{AZURE_AI_AGENT_NAME}' exists in the Foundry portal."
        )

    # ── Step 2: Create or reuse server-side conversation ───────────────────
    if not conversation_id:
        conversation = client.conversations.create()
        conversation_id = conversation.id
        print(f"[AssistantAgent] Created conversation: {conversation_id}")

    # ── Step 3: Initial agent call ──────────────────────────────────────────
    response = client.responses.create(
        conversation=conversation_id,
        extra_body={"agent_reference": AGENT_REFERENCE},
        input=[{"role": "user", "content": user_input}],
    )

    # ── Step 4: Autonomous multi-step tool execution loop ──────────────────
    max_steps = 3
    step = 0

    while step < max_steps:
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            break

        step += 1
        print(f"[ToolCalling] Step {step}: Executing {len(function_calls)} tool call(s)...")

        tool_outputs = []
        for call in function_calls:
            fn_name = call.name
            fn_args = json.loads(call.arguments)
            print(f"[ToolCalling] → '{fn_name}' with args {fn_args}")

            tool_fn = TOOL_MAP.get(fn_name)
            try:
                output = (
                    tool_fn(**fn_args)
                    if tool_fn
                    else json.dumps({"error": f"Tool '{fn_name}' not found in TOOL_MAP"})
                )
            except Exception as tool_err:
                # Always return an output — a missing output causes Responses API 400
                output = json.dumps({"error": f"Tool '{fn_name}' raised an exception: {str(tool_err)}"})
                print(f"[ToolCalling] ❌ '{fn_name}' failed: {tool_err}")

            tool_outputs.append({
                "type":    "function_call_output",
                "call_id": call.call_id,
                "output":  str(output),   # Always a string — never None
            })

        response = client.responses.create(
            conversation=conversation_id,
            extra_body={"agent_reference": AGENT_REFERENCE},
            input=tool_outputs,
        )

    final_text = response.output_text or ""
    return final_text, conversation_id
