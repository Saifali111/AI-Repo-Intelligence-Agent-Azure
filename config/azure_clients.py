"""
Azure Service Client Factory.
Provides initialized client instances for Azure OpenAI, Azure AI Foundry, and Azure AI Search.
"""

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
    """Initializes and returns the Azure OpenAI client."""
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
    """Initializes and returns the Azure AI Foundry Agent Service client using DefaultAzureCredential."""
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
    """Initializes and returns the Azure AI Search client for the specified index."""
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