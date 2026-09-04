"""
Azure AI Search Tools.
Provides vector semantic search over historical repository issues and codebase AST entities.
"""

import json
from azure.search.documents.models import VectorizedQuery
from config.azure_clients import get_azure_search_client, get_azure_openai_client
from config.settings import (
    AZURE_SEARCH_ISSUES_INDEX,
    AZURE_SEARCH_CODE_INDEX,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT
)

EMBEDDING_DIMENSIONS = 3072
RELEVANCE_THRESHOLD = 0.75
CANDIDATE_POOL_SIZE = 8


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generates dense vector embeddings for a list of texts using Azure OpenAI."""
    if not texts:
        return []

    client = get_azure_openai_client()
    if not client:
        print("[EmbeddingBatch] Azure OpenAI client not configured — using mock vectors.")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

    try:
        response = client.embeddings.create(
            input=texts,
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"[EmbeddingBatch] Failed to generate embeddings: {e}")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]


def get_query_embedding(query_text: str) -> list[float]:
    """Generates a dense vector embedding for a single search query string."""
    return get_embeddings_batch([query_text])[0]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculates exact cosine similarity between two vector embeddings."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_past_history(query: str) -> str:
    """Performs semantic vector search over historical repository issues with cosine threshold filtering."""
    print(f"[SearchTool] Searching past history for: '{query}'...")
    search_client = get_azure_search_client(AZURE_SEARCH_ISSUES_INDEX)

    if not search_client:
        return json.dumps({
            "status": "dry_run",
            "message": f"Simulated search for history matching '{query}'",
            "historical_matches": [
                {
                    "issue_number": 81204,
                    "title": "Similar App Router focus blur bug",
                    "similarity": 0.91,
                    "resolution": "Fixed by updating scroll/focus handler in router.ts (Resolved 6 months ago)"
                }
            ]
        }, indent=2)

    try:
        query_vector = get_query_embedding(query)

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=CANDIDATE_POOL_SIZE,
            fields="content_vector",
        )
        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["issue_number", "title", "state", "content", "content_vector"],
        )

        scored = []
        for doc in results:
            doc_vector = doc.get("content_vector")
            if not doc_vector:
                continue
            similarity = _cosine_similarity(query_vector, doc_vector)
            scored.append((similarity, doc))

        relevant = [(s, d) for s, d in scored if s >= RELEVANCE_THRESHOLD]

        if not relevant:
            best = max((s for s, _ in scored), default=0.0)
            print(f"[SearchTool] No match >= {RELEVANCE_THRESHOLD} threshold (best candidate: {best:.3f}).")
            return json.dumps({
                "historical_matches": [],
                "message": (
                    "No sufficiently relevant past issue was found in the index "
                    f"(best candidate similarity {best:.2f} was below the {RELEVANCE_THRESHOLD} "
                    "relevance threshold). Treat this as: no similar past issue exists. "
                    "Do not reference or speculate about any past issue for this query."
                ),
            }, indent=2)

        relevant.sort(key=lambda pair: pair[0], reverse=True)
        matches = []
        for similarity, doc in relevant:
            matches.append({
                "issue_number": doc.get("issue_number"),
                "title": doc.get("title"),
                "state": doc.get("state"),
                "similarity": round(similarity, 3),
                "summary": doc.get("content", "")[:400],
            })

        print(f"[SearchTool] Found {len(matches)} relevant match(es) >= {RELEVANCE_THRESHOLD} threshold.")
        return json.dumps({"historical_matches": matches}, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})


def search_codebase(query: str) -> str:
    """Searches the codebase index for matching files, classes, functions, and line numbers."""
    print(f"[SearchTool] Searching codebase for: '{query}'...")
    search_client = get_azure_search_client(AZURE_SEARCH_CODE_INDEX)

    if not search_client:
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
                "parent_class": doc.get("parent_class", ""),
                "function": doc.get("function_name", ""),
                "called_functions": doc.get("called_functions", ""),
                "start_line": doc.get("line_number"),
                "end_line": doc.get("end_line"),
                "code": doc.get("snippet", "")[:600]
            })
        return json.dumps({"code_matches": matches}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Codebase search failed: {str(e)}"})


if __name__ == "__main__":
    print("=== Testing Search Tools ===")
    print(search_past_history("router push focus blur"))
    print("---------------------------------")
    print(search_codebase("handleFocusBlur app-router"))