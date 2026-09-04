"""
Maintainer Assistant Agent.
Invokes the Azure AI Foundry assistant agent via the Responses API and executes custom function tools.
"""

import json
import requests
from opentelemetry import trace

from config.azure_clients import get_agent_openai_client
from config.settings import (
    AZURE_AI_AGENT_NAME,
    AZURE_CONTENT_SAFETY_ENDPOINT,
    AZURE_CONTENT_SAFETY_KEY,
)
from tools.github_tools import (
    fetch_live_issue_and_comments,
    fetch_live_pr_details,
    fetch_ci_build_logs,
)
from tools.search_tools import search_past_history, search_codebase

tracer = trace.get_tracer("devpulse.assistant")

AGENT_REFERENCE = {
    "name": AZURE_AI_AGENT_NAME,
    "type": "agent_reference",
}

TOOL_MAP = {
    "fetch_live_issue_and_comments": fetch_live_issue_and_comments,
    "fetch_live_pr_details": fetch_live_pr_details,
    "fetch_ci_build_logs": fetch_ci_build_logs,
    "search_past_history": search_past_history,
    "search_codebase": search_codebase,
}


def screen_input_safety(text: str) -> bool:
    """Pre-screens user input with Azure AI Content Safety to filter harmful content."""
    if not AZURE_CONTENT_SAFETY_ENDPOINT or not AZURE_CONTENT_SAFETY_KEY:
        print("[ContentSafety] Not configured — skipping pre-screen.")
        return True

    url = f"{AZURE_CONTENT_SAFETY_ENDPOINT.rstrip('/')}/contentsafety/text:analyze?api-version=2023-10-01"
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_CONTENT_SAFETY_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "categories": ["Hate", "SelfHarm", "Sexual", "Violence"],
        "haltOnBlocklistHit": True,
        "outputType": "FourSeverityLevels",
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=5)
        if res.status_code == 200:
            analysis = res.json()
            for cat_result in analysis.get("categoriesAnalysis", []):
                if cat_result.get("severity", 0) >= 2:
                    print(f"[ContentSafety] ⚠️ Input blocked by category: {cat_result.get('category')}")
                    return False
            return True
        else:
            print(f"[ContentSafety] API error {res.status_code}: {res.text}. Failing open.")
            return True
    except Exception as e:
        print(f"[ContentSafety] Check failed: {e}. Failing open.")
        return True


def run_maintainer_assistant(user_input: str, conversation_id: str = None) -> tuple[str, str]:
    """Runs the Assistant Agent in Azure AI Foundry and executes the tool-calling loop."""
    print(f"[AssistantAgent] Processing input: '{user_input[:80]}...'")

    # Pre-screen input safety
    if not screen_input_safety(user_input):
        return (
            "⚠️ Your query was flagged by the content safety filter and cannot be processed. "
            "Please rephrase your question.",
            conversation_id or "",
        )

    # Initialize client
    client = get_agent_openai_client()
    if not client:
        raise RuntimeError(
            "[AssistantAgent Error] Foundry Agent client is not configured. "
            "Check AZURE_AI_PROJECT_ENDPOINT in your .env and ensure the agent "
            f"'{AZURE_AI_AGENT_NAME}' exists in the Foundry portal."
        )

    # Create or reuse conversation thread
    if not conversation_id:
        conversation = client.conversations.create()
        conversation_id = conversation.id
        print(f"[AssistantAgent] Created conversation: {conversation_id}")

    # Send initial user message
    try:
        response = client.responses.create(
            conversation=conversation_id,
            extra_body={"agent_reference": AGENT_REFERENCE},
            input=[{"role": "user", "content": user_input}],
        )
    except Exception as e:
        print(f"[AssistantAgent] Re-creating fresh conversation due to pending state...")
        conversation = client.conversations.create()
        conversation_id = conversation.id
        response = client.responses.create(
            conversation=conversation_id,
            extra_body={"agent_reference": AGENT_REFERENCE},
            input=[{"role": "user", "content": user_input}],
        )

    # Multi-step tool execution loop
    max_steps = 6
    step = 0

    while step < max_steps:
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            break

        step += 1
        print(f"[ToolCalling] Step {step}: Executing {len(function_calls)} tool call(s)...")

        tool_outputs = []
        for call in function_calls:
            call_id = getattr(call, "call_id", None) or getattr(call, "id", None)
            if not call_id and isinstance(call, dict):
                call_id = call.get("call_id") or call.get("id")

            fn_name = getattr(call, "name", None) or (call.get("name") if isinstance(call, dict) else "")
            raw_args = getattr(call, "arguments", None) or (call.get("arguments") if isinstance(call, dict) else "{}")

            try:
                fn_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args or {})
            except Exception:
                fn_args = {}

            print(f"[ToolCalling] → '{fn_name}' (ID: {call_id}) with args {fn_args}")
            tool_fn = TOOL_MAP.get(fn_name)

            output = ""
            try:
                with tracer.start_as_current_span(f"tool:{fn_name}") as span:
                    span.set_attribute("tool.name", fn_name)
                    span.set_attribute("tool.arguments", str(fn_args)[:200])

                    if tool_fn:
                        output = tool_fn(**fn_args)
                    else:
                        output = json.dumps({"error": f"Tool '{fn_name}' not found in TOOL_MAP"})
            except Exception as tool_err:
                output = json.dumps({"error": f"Tool '{fn_name}' raised an exception: {str(tool_err)}"})
                print(f"[ToolCalling] ❌ '{fn_name}' failed: {tool_err}")

            tool_outputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": str(output),
            })

        response = client.responses.create(
            conversation=conversation_id,
            extra_body={"agent_reference": AGENT_REFERENCE},
            input=tool_outputs,
        )

    # Extract response text
    final_text = response.output_text or ""
    if not final_text and hasattr(response, "output"):
        for item in response.output:
            if getattr(item, "type", "") == "message":
                for part in getattr(item, "content", []):
                    if getattr(part, "type", "") == "text":
                        final_text += getattr(part, "text", "")

    return final_text, conversation_id
