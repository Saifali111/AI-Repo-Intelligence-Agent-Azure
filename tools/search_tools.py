import json
from config.azure_clients import get_azure_search_client, get_azure_openai_client
from config.settings import (
    AZURE_SEARCH_ISSUES_INDEX,
    AZURE_SEARCH_HISTORY_INDEX,
    AZURE_SEARCH_CODE_INDEX,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT
)


def get_query_embedding(query_text: str):
    """Generates vector embedding for a search query using Azure OpenAI."""
    client = get_azure_openai_client()
    if not client:
        # Return mock embedding vector if Azure key is not configured yet
        return [0.0] * 1536
    
    try:
        response = client.embeddings.create(
            input=query_text,
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[EmbeddingError] Failed to generate embedding: {e}")
        return [0.0] * 1536


def search_past_history(query: str) -> str:
    """
    Queries issues-index and briefings-history to check if similar bugs occurred previously.
    """
    print(f"[SearchTool] Searching past history for: '{query}'...")
    search_client = get_azure_search_client(AZURE_SEARCH_ISSUES_INDEX)
    
    if not search_client:
        # Dry-run fallback response when Azure AI Search is not yet deployed
        return json.dumps({
            "status": "dry_run",
            "message": f"Simulated search for history matching '{query}'",
            "historical_matches": [
                {
                    "issue_number": 81204,
                    "title": "Similar App Router focus blur bug",
                    "resolution": "Fixed by updating scroll/focus handler in router.ts (Resolved 6 months ago)"
                }
            ]
        }, indent=2)
    
    try:
        results = search_client.search(
            search_text=query,
            top=3
        )
        matches = []
        for doc in results:
            matches.append({
                "issue_number": doc.get("issue_number"),
                "title": doc.get("title"),
                "state": doc.get("state"),
                "summary": doc.get("content", "")[:400]
            })
        return json.dumps({"historical_matches": matches}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})


def search_codebase(query: str) -> str:
    """
    Queries codebase-index to locate source code files and line numbers.
    """
    print(f"[SearchTool] Searching codebase for: '{query}'...")
    search_client = get_azure_search_client(AZURE_SEARCH_CODE_INDEX)
    
    if not search_client:
        # Dry-run fallback response when Azure AI Search is not yet deployed
        return json.dumps({
            "status": "dry_run",
            "message": f"Simulated codebase search for '{query}'",
            "code_matches": [
                {
                    "file_path": "packages/next/src/client/components/app-router.tsx",
                    "line_number": 142,
                    "snippet": "handleFocusBlur(event) { if (!event.target) return; ... }"
                }
            ]
        }, indent=2)
    
    try:
        results = search_client.search(
            search_text=query,
            top=3
        )
        matches = []
        for doc in results:
            matches.append({
                "file": doc.get("file_path"),
                "language": doc.get("language"),
                "line": doc.get("line_number"),
                "code": doc.get("snippet", "")[:500]
            })
        return json.dumps({"code_matches": matches}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Codebase search failed: {str(e)}"})

if __name__ == "__main__":
    # print(get_query_embedding("router push focus blur"))
    print("=== Testing Search Tools ===")
    print(search_past_history("router push focus blur"))
    print("---------------------------------")
    print(search_codebase("handleFocusBlur app-router"))
