from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_AI_PROJECT_ENDPOINT,
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_ISSUES_INDEX,
    AZURE_SEARCH_CODE_INDEX,
)

def get_azure_openai_client():
    """Initializes and returns Azure OpenAI Client."""
    if not AZURE_OPENAI_KEY:
        print("[AzureClients] Warning: AZURE_OPENAI_KEY is not set. Operating in dry-run mode.")
        return None
    try:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )
    except Exception as e:
        print(f"[AzureClients] Error initializing AzureOpenAI client: {e}")
        return None


def get_agent_openai_client():
    """
    Initializes the Foundry Agent Service client used for the Responses API
    (client.responses.create(..., extra_body={"agent_reference": ...})).

    This is NOT the same thing as get_azure_openai_client() above:
    - It targets the Foundry *project* endpoint, not the AOAI resource endpoint.
    - It authenticates with Azure AD (DefaultAzureCredential), not an API key.
    - It requires the agent to already exist in the Foundry portal/project
      (Agents section) under AZURE_AI_AGENT_NAME.
    Requires: pip install azure-ai-projects azure-identity
    """
    if not AZURE_AI_PROJECT_ENDPOINT:
        print("[AzureClients] Warning: AZURE_AI_PROJECT_ENDPOINT is not set. Operating in dry-run mode.")
        return None
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project = AIProjectClient(
            endpoint=AZURE_AI_PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        return project.get_openai_client()
    except Exception as e:
        print(f"[AzureClients] Error initializing Foundry Agent client: {e}")
        return None


def get_azure_search_client(index_name=None):
    """Initializes and returns Azure AI Search Client for a specified index."""
    target_index = index_name or AZURE_SEARCH_ISSUES_INDEX
    if not AZURE_SEARCH_KEY:
        print(f"[AzureClients] Warning: AZURE_SEARCH_KEY is not set for '{target_index}'. Operating in dry-run mode.")
        return None
    try:
        from azure.search.documents import SearchClient
        from azure.core.credentials import AzureKeyCredential
        return SearchClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=target_index,
            credential=AzureKeyCredential(AZURE_SEARCH_KEY)
        )
    except Exception as e:
        print(f"[AzureClients] Error initializing SearchClient for '{target_index}': {e}")
        return None



if __name__ == "__main__":
    print("=== Testing Azure Configuration Setup ===")
    print(f"OpenAI Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"Search Endpoint: {AZURE_SEARCH_ENDPOINT}")
    print(f"Issues Index: {AZURE_SEARCH_ISSUES_INDEX}")
    print(f"Codebase Index: {AZURE_SEARCH_CODE_INDEX}")