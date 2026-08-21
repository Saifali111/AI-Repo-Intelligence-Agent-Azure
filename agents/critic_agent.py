from enum import Enum
from pydantic import BaseModel, Field
from config.azure_clients import get_azure_openai_client
from config.settings import AZURE_OPENAI_MINI_DEPLOYMENT


class QueryIntent(str, Enum):
    ISSUE_ANALYSIS = "ISSUE_ANALYSIS"
    PR_REVIEW = "PR_REVIEW"
    CI_BUILD_DEBUG = "CI_BUILD_DEBUG"
    GENERAL_QUERY = "GENERAL_QUERY"


class CriticEvaluation(BaseModel):
    """Structured response schema returned by Azure OpenAI gpt-4o-mini."""
    intent: QueryIntent = Field(description="Detected query intent (ISSUE_ANALYSIS, PR_REVIEW, CI_BUILD_DEBUG, GENERAL_QUERY).")
    is_safe: bool = Field(description="True if draft passes content safety and prompt injection checks.")
    has_required_sections: bool = Field(description="True if response contains required sections for its detected intent.")
    is_grounded: bool = Field(description="True if claims are backed by tool output without hallucinations.")
    approved: bool = Field(description="True if is_safe, has_required_sections, and is_grounded are all True.")
    feedback: str = Field(description="Specific actionable feedback detailing what to fix if rejected, or empty if approved.")


def evaluate_draft_response(draft_text: str, user_query: str = "") -> CriticEvaluation:
    """
    Evaluates a draft response using Azure OpenAI gpt-4o-mini with dynamic query intent validation.
    Raises RuntimeError if Azure client is not configured.
    """
    print(f"[CriticAgent] Evaluating draft response for query: '{user_query}'...")
    client = get_azure_openai_client()

    if not client:
        raise RuntimeError(
            "[CriticAgent Error] Azure OpenAI client is not configured. "
            "Please check AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT in your environment / .env file."
        )

    try:
        # Call Azure OpenAI gpt-4o-mini with Structured Outputs
        completion = client.beta.chat.completions.parse(
            model=AZURE_OPENAI_MINI_DEPLOYMENT,
            messages=[
                {"role": "user", "content": f"User Query: {user_query}\n\nDraft Response to Evaluate:\n{draft_text}"}
            ],
            response_format=CriticEvaluation
        )
        
        evaluation: CriticEvaluation = completion.choices[0].message.parsed
        print(f"[CriticAgent] Intent: {evaluation.intent.value} | Approved: {evaluation.approved}")
        return evaluation

    except Exception as e:
        print(f"[CriticAgent] Evaluation failed: {e}")
        raise e
