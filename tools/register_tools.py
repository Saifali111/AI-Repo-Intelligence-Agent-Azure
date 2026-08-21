"""
One-time setup script: registers the 5 custom function tools on the existing
`assistant-agent` in Foundry.

WHY THIS SCRIPT EXISTS:
The Foundry portal deliberately does not support adding, removing, or updating
function tool definitions through the UI -- only the SDK/REST API can do it.
(Portal "Custom" tab only offers OpenAPI / MCP / Agent2Agent, none of which fit
a plain Python function.) This script does what the portal can't.

Run this ONCE (and again any time you change a tool's name/parameters):
    python3 -m scripts.register_tools

It creates a NEW VERSION of your existing agent -- same name ("assistant-agent").
Instructions are NOT hardcoded here: this script fetches whatever is currently
published in the portal and reuses it as-is, then adds the 5 tools on top.
The portal stays the single source of truth for instructions; this script only
ever touches tools. Your .env AZURE_AI_AGENT_NAME does not need to change.
"""
import sys
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool

from config.settings import AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_AGENT_NAME, AZURE_OPENAI_DEPLOYMENT_NAME

TOOLS = [
    FunctionTool(
        name="fetch_live_issue_and_comments",
        description="Fetch live issue details and discussion comments from GitHub",
        parameters={
            "type": "object",
            "properties": {"issue_number": {"type": "integer"}},
            "required": ["issue_number"],
        },
        strict=False,
    ),
    FunctionTool(
        name="fetch_live_pr_details",
        description="Fetch live Pull Request details, status, and changed files",
        parameters={
            "type": "object",
            "properties": {"pr_number": {"type": "integer"}},
            "required": ["pr_number"],
        },
        strict=False,
    ),
    FunctionTool(
        name="fetch_ci_build_logs",
        description="Fetch GitHub Actions CI build run status and error tracebacks for a PR",
        parameters={
            "type": "object",
            "properties": {"pr_number": {"type": "integer"}},
            "required": ["pr_number"],
        },
        strict=False,
    ),
    FunctionTool(
        name="search_past_history",
        description="Query historical memory to check if a similar bug occurred previously",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        strict=False,
    ),
    FunctionTool(
        name="search_codebase",
        description="Query codebase index for source code file paths and line numbers",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        strict=False,
    ),
]


def main():
    if not AZURE_AI_PROJECT_ENDPOINT:
        print("ERROR: AZURE_AI_PROJECT_ENDPOINT is not set in .env")
        sys.exit(1)

    project = AIProjectClient(
        endpoint=AZURE_AI_PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    print(f"Fetching current published definition for agent '{AZURE_AI_AGENT_NAME}'...")
    current = project.agents.get(agent_name=AZURE_AI_AGENT_NAME)
    current_def = current["versions"]["latest"]["definition"]

    print(f"Found existing agent. Model: {current_def.get('model')!r}")
    print(f"Existing instructions (first 80 chars): {str(current_def.get('instructions'))[:80]!r}...")
    print(f"Creating new version with {len(TOOLS)} tools added on top of the existing instructions...")

    version = project.agents.create_version(
        agent_name=AZURE_AI_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=current_def.get("model", AZURE_OPENAI_DEPLOYMENT_NAME),
            instructions=current_def.get("instructions"),
            tools=TOOLS,
        ),
    )

    print(f"✅ Created version: {version}")
    print("Go to the portal, open assistant-agent, and click Publish to make this version live.")


if __name__ == "__main__":
    main()