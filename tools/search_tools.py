import json
from azure.search.documents.models import VectorizedQuery
from config.azure_clients import get_azure_search_client, get_azure_openai_client
from config.settings import (
    AZURE_SEARCH_ISSUES_INDEX,
    AZURE_SEARCH_CODE_INDEX,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT
)

# text-embedding-3-large produces 3072-dimensional vectors by default.
# Must match EMBEDDING_DIMENSIONS in scripts/create_indexes.py exactly, or
# Azure AI Search will reject uploads with a dimension-mismatch error.
EMBEDDING_DIMENSIONS = 3072

# Minimum EXACT cosine similarity (not Azure's transformed @search.score --
# see _cosine_similarity() below) for a past issue to count as "relevant."
# Below this, search_past_history() reports no match rather than returning
# a weak candidate the assistant might mistake for a real precedent.
RELEVANCE_THRESHOLD = 0.75

# How many approximate-nearest-neighbor candidates to pull from Azure before
# re-filtering by exact cosine similarity. Kept larger than 1 so a good match
# isn't lost to HNSW's approximation before we get to judge it precisely.
CANDIDATE_POOL_SIZE = 8


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Embeds a LIST of texts in a single Azure OpenAI API call.
    Used at ingest time, where we're embedding many issues at once —
    one call per batch instead of one call per document.
    Returns a list of vectors in the same order as `texts`.
    Falls back to mock (all-zero) vectors if the client isn't configured,
    so ingestion can still be dry-run tested without live credentials.
    """
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
        # response.data is returned in the same order as the input list
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"[EmbeddingBatch] Failed to generate embeddings: {e}")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]


def get_query_embedding(query_text: str) -> list[float]:
    """Generates a vector embedding for a single query string. Thin wrapper
    around get_embeddings_batch() so single- and batch-embedding always stay
    dimensionally consistent with each other."""
    return get_embeddings_batch([query_text])[0]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Exact cosine similarity between two vectors, computed directly rather
    than relying on Azure AI Search's returned @search.score.

    WHY: for vector queries with the cosine metric, Azure does NOT return
    raw cosine similarity in @search.score. Per Microsoft's own docs, it
    returns a transformed, monotonically-decreasing value:
        @search.score = 1 / (1 + cosine_distance)   where cosine_distance = 1 - cosine_similarity
    So a @search.score of 0.75 actually corresponds to a real cosine
    similarity of ~0.667, not 0.75. Recomputing it ourselves means a
    threshold of 0.75 here means literally that -- no mental conversion,
    no ambiguity, and no dependency on undocumented score behavior.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_past_history(query: str) -> str:
    """
    Semantic search over devpulse-issues-index: embeds the query, retrieves
    an approximate-nearest-neighbor candidate pool from Azure, then re-scores
    each candidate with exact cosine similarity and keeps only matches at or
    above RELEVANCE_THRESHOLD (0.75).

    If nothing clears the threshold, returns an explicit "no relevant match"
    result rather than the closest-available-but-still-weak candidates --
    the assistant should treat this as "no similar past issue," not as
    missing data to guess at.
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
    """
    Queries codebase-index to locate source code files and line numbers.
    (Unchanged in this step -- GraphRAG-based rework is a separate step.)
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