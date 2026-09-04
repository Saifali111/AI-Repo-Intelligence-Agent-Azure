"""
Azure AI Search Index Setup.
Creates and configures search indexes for historical issues, AST codebase entries, and pull requests.
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

EMBEDDING_DIMENSIONS = 3072
VECTOR_SEARCH_PROFILE_NAME = "devpulse-vector-profile"
VECTOR_SEARCH_ALGORITHM_NAME = "devpulse-hnsw"


def get_vector_search_config() -> VectorSearch:
    """Configures HNSW vector search algorithm and profile for embedding fields."""
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
    """Initializes and returns the SearchIndexClient."""
    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY is not set in .env")
        sys.exit(1)
    return SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def build_issues_index() -> SearchIndex:
    """Defines the search index schema for historical GitHub issues with vector search."""
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
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=True,
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
    """Defines the search index schema for AST-parsed codebase source code entities."""
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
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=VECTOR_SEARCH_PROFILE_NAME,
        ),
    ]
    return SearchIndex(
        name=AZURE_SEARCH_CODE_INDEX,
        fields=fields,
        vector_search=get_vector_search_config(),
        cors_options=CorsOptions(allowed_origins=["*"])
    )


def build_prs_index() -> SearchIndex:
    """Defines the search index schema for historical Pull Requests."""
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
    """Initializes and recreates search indexes in Azure AI Search."""
    print("=== DevPulse: Creating Azure AI Search Indexes ===\n")
    client = get_index_client()
    for label, builder_fn in INDEXES:
        index_def = builder_fn()
        print(f"[{label}] Resetting '{index_def.name}'...")
        try:
            try:
                client.delete_index(index_def.name)
                print(f"  🗑️ Deleted old '{index_def.name}'.")
            except Exception:
                pass

            result = client.create_index(index_def)
            print(f"  ✅ Fresh '{result.name}' created ({len(result.fields)} fields).\n")
        except Exception as e:
            print(f"  ❌ Failed: {e}\n")


if __name__ == "__main__":
    main()