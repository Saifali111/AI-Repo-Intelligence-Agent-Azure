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
)
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY,
    AZURE_SEARCH_ISSUES_INDEX, AZURE_SEARCH_HISTORY_INDEX,
    AZURE_SEARCH_CODE_INDEX, AZURE_SEARCH_PRS_INDEX,
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
    """devpulse-issues-index — historical GitHub issues."""
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
    ]
    return SearchIndex(name=AZURE_SEARCH_ISSUES_INDEX, fields=fields,
                       cors_options=CorsOptions(allowed_origins=["*"]))


def build_history_index() -> SearchIndex:
    """devpulse-briefings-history — maintainer resolution notes."""
    fields = [
        SimpleField(name="id",          type=SearchFieldDataType.String,  key=True, filterable=True),
        SearchableField(name="title",   type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="content", type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SimpleField(name="date",        type=SearchFieldDataType.String,  sortable=True),
        SimpleField(name="issue_refs",  type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="author",      type=SearchFieldDataType.String,  filterable=True),
    ]
    return SearchIndex(name=AZURE_SEARCH_HISTORY_INDEX, fields=fields,
                       cors_options=CorsOptions(allowed_origins=["*"]))


def build_codebase_index() -> SearchIndex:
    """devpulse-codebase-index — chunked source code for code-location search."""
    fields = [
        SimpleField(name="id",               type=SearchFieldDataType.String,  key=True, filterable=True),
        SearchableField(name="file_path",    type=SearchFieldDataType.String,  analyzer_name="keyword"),
        SimpleField(name="line_number",      type=SearchFieldDataType.Int32,   filterable=True, sortable=True),
        SearchableField(name="function_name",type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="snippet",      type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SearchableField(name="content",      type=SearchFieldDataType.String,  analyzer_name="en.microsoft"),
        SimpleField(name="language",         type=SearchFieldDataType.String,  filterable=True),
        SimpleField(name="repo",             type=SearchFieldDataType.String,  filterable=True),
    ]
    return SearchIndex(name=AZURE_SEARCH_CODE_INDEX, fields=fields,
                       cors_options=CorsOptions(allowed_origins=["*"]))


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
    ("Briefings History", build_history_index),
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
