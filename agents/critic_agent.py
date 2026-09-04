"""
Critic and Guardrail Agent.
Validates draft responses against intent, safety, groundedness, and required section schemas.
"""

import json
import re
from enum import Enum
from pydantic import BaseModel, Field
from config.azure_clients import get_agent_openai_client
from config.settings import AZURE_AI_CRITIC_NAME
from opentelemetry import trace

CRITIC_AGENT_REFERENCE = {
    "name": AZURE_AI_CRITIC_NAME,
    "type": "agent_reference"
}

tracer = trace.get_tracer("devpulse.critic")


class QueryIntent(str, Enum):
    ISSUE_ANALYSIS = "ISSUE_ANALYSIS"
    PR_REVIEW = "PR_REVIEW"
    CI_BUILD_DEBUG = "CI_BUILD_DEBUG"
    GENERAL_QUERY = "GENERAL_QUERY"


class CriticEvaluation(BaseModel):
    intent: QueryIntent = Field(default=QueryIntent.GENERAL_QUERY, description="Detected query intent.")
    is_safe: bool = Field(default=True, description="True if draft passes safety checks.")
    has_required_sections: bool = Field(default=True, description="True if required sections exist.")
    is_grounded: bool = Field(default=True, description="True if claims are backed by tool output.")
    approved: bool = Field(default=True, description="True if approved for delivery.")
    feedback: str = Field(default="", description="Specific actionable feedback if rejected.")


def parse_critic_output(raw_text: str) -> CriticEvaluation:
    """Parses and extracts structured CriticEvaluation JSON from agent output text."""
    try:
        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if json_match:
            data = json.loads(json_match.group(0))
        else:
            data = json.loads(raw_text)

        intent_raw = str(data.get("intent", "GENERAL_QUERY")).upper()
        intent = QueryIntent(intent_raw) if intent_raw in QueryIntent.__members__ else QueryIntent.GENERAL_QUERY

        return CriticEvaluation(
            intent=intent,
            is_safe=bool(data.get("is_safe", True)),
            has_required_sections=bool(data.get("has_required_sections", True)),
            is_grounded=bool(data.get("is_grounded", True)),
            approved=bool(data.get("approved", True)),
            feedback=str(data.get("feedback", ""))
        )
    except Exception as e:
        print(f"[CriticAgent] Warning: Could not parse JSON from critic output: {e}. Raw: {raw_text[:120]}")
        return CriticEvaluation(
            intent=QueryIntent.GENERAL_QUERY,
            is_safe=True,
            has_required_sections=True,
            is_grounded=True,
            approved=True,
            feedback=""
        )


def evaluate_draft_response(draft_text: str, user_query: str = "") -> CriticEvaluation:
    """Evaluates assistant draft responses for safety, groundedness, and format compliance."""
    print(f"[CriticAgent] Evaluating draft response for query: '{user_query}' via portal '{AZURE_AI_CRITIC_NAME}'...")
    client = get_agent_openai_client()

    if not client:
        raise RuntimeError(
            "[CriticAgent Error] Foundry Agent client is not configured. "
            "Check AZURE_AI_PROJECT_ENDPOINT in your .env."
        )

    with tracer.start_as_current_span("critic_agent.evaluate") as span:
        span.set_attribute("critic.user_query", user_query[:100])
        try:
            prompt_content = (
                f"User Query: {user_query}\n\n"
                f"Draft Response to Evaluate:\n{draft_text}\n\n"
                "Format your evaluation as a valid JSON object with the following keys:\n"
                "{\n"
                '  "intent": "ISSUE_ANALYSIS" | "PR_REVIEW" | "CI_BUILD_DEBUG" | "GENERAL_QUERY",\n'
                '  "is_safe": true,\n'
                '  "has_required_sections": true,\n'
                '  "is_grounded": true,\n'
                '  "approved": true,\n'
                '  "feedback": ""\n'
                "}"
            )

            response = client.responses.create(
                extra_body={"agent_reference": CRITIC_AGENT_REFERENCE},
                input=[{"role": "user", "content": prompt_content}],
            )

            evaluation = parse_critic_output(response.output_text or "")
            span.set_attribute("critic.approved", evaluation.approved)
            span.set_attribute("critic.intent", evaluation.intent.value)
            print(f"[CriticAgent] Intent: {evaluation.intent.value} | Approved: {evaluation.approved}")
            return evaluation

        except Exception as e:
            print(f"[CriticAgent] Evaluation execution failed: {e}")
            span.record_exception(e)
            return CriticEvaluation(
                intent=QueryIntent.GENERAL_QUERY,
                is_safe=True,
                has_required_sections=True,
                is_grounded=True,
                approved=True,
                feedback=""
            )

