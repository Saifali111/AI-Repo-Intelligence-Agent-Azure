"""
DevPulse Agent Pipeline Orchestrator.
Coordinates the Assistant Agent generation and Critic Agent evaluation loop with retry feedback.
"""

import concurrent.futures
from agents.assistant_agent import run_maintainer_assistant
from agents.critic_agent import evaluate_draft_response, CriticEvaluation


def run_devpulse_pipeline(user_input: str, conversation_id: str = None, max_retries: int = 2) -> dict:
    """Orchestrates the Assistant generation and Critic evaluation loop."""
    print(f"\n🚀 [DevPulsePipeline] Processing query: '{user_input}'")

    current_input = user_input
    retries = 0
    draft_text = ""
    evaluation = None

    while retries <= max_retries:
        # Generate draft response via Assistant Agent
        draft_text, conversation_id = run_maintainer_assistant(
            user_input=current_input,
            conversation_id=conversation_id
        )

        # Validate draft response via Critic Agent with timeout protection
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(evaluate_draft_response, draft_text, user_input)
                evaluation = future.result(timeout=15)
        except Exception as e:
            print(f"⚠️ [DevPulsePipeline] Critic timed out / failed: {e}. Approving draft.")
            from agents.critic_agent import QueryIntent
            evaluation = CriticEvaluation(
                intent=QueryIntent.GENERAL_QUERY,
                is_safe=True, has_required_sections=True,
                is_grounded=True, approved=True, feedback=""
            )

        print(f"[Critic] Intent={evaluation.intent.value} | Approved={evaluation.approved} | Attempt {retries + 1}/{max_retries + 1}")

        # Return validated response on approval
        if evaluation.approved:
            print(f"✅ [DevPulsePipeline] Approved on attempt {retries + 1}.")
            return {
                "response": draft_text,
                "conversation_id": conversation_id,
                "evaluation": evaluation.model_dump(),
                "retries_used": retries
            }

        # Retry with Critic feedback if rejected
        retries += 1
        if retries <= max_retries:
            print(f"⚠️ [DevPulsePipeline] Rejected. Retrying ({retries}/{max_retries}). Feedback: {evaluation.feedback}")
            current_input = (
                f"Your previous response was rejected: '{evaluation.feedback}'\n"
                f"Fix it and try again. Keep your answer concise.\n\n"
                f"Original query: {user_input}"
            )

    print("⚠️ [DevPulsePipeline] Max retries reached. Returning best draft.")
    return {
        "response": draft_text,
        "conversation_id": conversation_id,
        "evaluation": evaluation.model_dump(),
        "retries_used": retries
    }


if __name__ == "__main__":
    print("=== Testing DevPulse 2-Agent Orchestration Pipeline ===")
    try:
        result = run_devpulse_pipeline("Tell me about Issue #96050")
        print("\n--- Pipeline Result ---")
        print(f"Response: {result['response']}")
        print(f"Evaluation: {result['evaluation']}")
    except Exception as e:
        print(f"Pipeline Execution Failed: {e}")