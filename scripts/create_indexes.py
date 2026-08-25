"""
Step 1 Setup: Create all 4 Azure AI Search indexes for DevPulse.

Run once:
    python3 -m scripts.create_indexes
"""

import sys
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SimpleField, SearchableField, CorsOptions,
    VectorSearch, VectorSearchProfile, HnswAlgorithmConfiguration,
)
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY,
    AZURE_SEARCH_ISSUES_INDEX,
    AZURE_SEARCH_CODE_INDEX, AZURE_SEARCH_PRS_INDEX,
)

# text-embedding-3-large produces 3072-dimensional vectors by default.
# NOTE: this must match whatever get_query_embedding() actually returns —
# its current dry-run fallback returns a 1536-dim mock vector, which will
# need updating to 3072 in the next step so shapes agree end to end.
EMBEDDING_DIMENSIONS = 3072

VECTOR_SEARCH_PROFILE_NAME = "devpulse-vector-profile"
VECTOR_SEARCH_ALGORITHM_NAME = "devpulse-hnsw"


def get_vector_search_config() -> VectorSearch:
    """
    Defines HOW vector search is performed: the HNSW approximate-nearest-
    neighbor algorithm, wrapped in a named "profile" that fields reference.
    HNSW trades a small amount of recall for much faster query time than
    exhaustive (brute-force) k-NN — the right default for this scale of data.
    """
    return VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name=VECTOR_SEARCH_ALGORITHM_NAME),
        ],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_SEARCH_PROFILE_NAME,
                algorithm_configuration_name=VECTOR_SEARCH_ALGORITHM_NAME,
            ),
        ],
    )


def get_index_client() -> SearchIndexClient:
    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY is not set in .env")
        sys.exit(1)
    return SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def build_issues_index() -> SearchIndex:
    """devpulse-issues-index — historical GitHub issues, now with a vector
    field for semantic similarity search alongside the existing keyword fields."""
    fields = [
        SimpleField(name="id",                 type=SearchFieldDataType.String,  key=True,       filterable=True),
        SimpleField(name="issue_number",        type=SearchFieldDataType.Int32,                   filterable=True, sortable=True),
        SearchableField(name="title",           type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="body",            type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="content",         type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SimpleField(name="state",               type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="author",              type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="labels",              type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="created_at",          type=SearchFieldDataType.String,  sortable=True),
        SimpleField(name="closed_at",           type=SearchFieldDataType.String,  sortable=True),
        SearchableField(name="resolution_summary", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        # Vector field: embedding of `content` (title + body), used for
        # semantic similarity search instead of/alongside keyword matching.
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=True,  # SDK/REST defaults this to False for vector fields (portal wizard defaults True) — we need it back to compute exact cosine similarity ourselves in search_past_history()
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=VECTOR_SEARCH_PROFILE_NAME,
        ),
    ]
    return SearchIndex(
        name=AZURE_SEARCH_ISSUES_INDEX,
        fields=fields,
        vector_search=get_vector_search_config(),
        cors_options=CorsOptions(allowed_origins=["*"]),
    )


def build_codebase_index() -> SearchIndex:
    """devpulse-codebase-index — AST-chunked source code with relational metadata."""
    fields = [
        SimpleField(name="id",                 type=SearchFieldDataType.String,  key=True, filterable=True),
        SearchableField(name="file_path",      type=SearchFieldDataType.String,  analyzer_name="keyword"),
        SimpleField(name="line_number",        type=SearchFieldDataType.Int32,   filterable=True, sortable=True),
        SimpleField(name="end_line",           type=SearchFieldDataType.Int32,   filterable=True, sortable=True),
        SearchableField(name="parent_class",   type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="function_name",  type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="called_functions", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SearchableField(name="imports",        type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="snippet",        type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="content",        type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SimpleField(name="language",           type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="repo",               type=SearchFieldDataType.String,  filterable=True),
    ]
    return SearchIndex(
        name=AZURE_SEARCH_CODE_INDEX,
        fields=fields,
        cors_options=CorsOptions(allowed_origins=["*"])
    )



def build_prs_index() -> SearchIndex:
    """devpulse-prs-index — historical Pull Requests."""
    fields = [
        SimpleField(name="id",            type=SearchFieldDataType.String,  key=True, filterable=True),
        SimpleField(name="pr_number",     type=SearchFieldDataType.Int32,   filterable=True, sortable=True),
        SearchableField(name="title",     type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="body",      type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="content",   type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SimpleField(name="state",         type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="author",        type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="merged",        type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="created_at",    type=SearchFieldDataType.String,  sortable=True),
        SimpleField(name="merged_at",     type=SearchFieldDataType.String,  sortable=True),
        SimpleField(name="changed_files", type=SearchFieldDataType.String),
    ]
    return SearchIndex(name=AZURE_SEARCH_PRS_INDEX, fields=fields,
                       cors_options=CorsOptions(allowed_origins=["*"]))


INDEXES = [
    ("Issues Index",      build_issues_index),
    ("Codebase Index",    build_codebase_index),
    ("PRs Index",         build_prs_index),
]


def main():
    print("=== DevPulse: Creating Azure AI Search Indexes ===\n")
    client = get_index_client()
    for label, builder_fn in INDEXES:
        index_def = builder_fn()
        print(f"[{label}] Creating '{index_def.name}'...")
        try:
            result = client.create_or_update_index(index_def)
            print(f"  ✅ '{result.name}' ready — {len(result.fields)} fields.\n")
        except Exception as e:
            print(f"  ❌ Failed: {e}\n")
    print("=== Done. Next: python3 -m scripts.ingest_history ===")


if __name__ == "__main__":
    main()