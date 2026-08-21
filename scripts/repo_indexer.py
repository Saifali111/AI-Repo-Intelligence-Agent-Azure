"""
Step 3: Clone a GitHub repo and index source code into devpulse-codebase-index.

Run:
    python3 -m scripts.repo_indexer

What it does:
  - Clones the target GitHub repo into a temp directory
  - Walks all source files (.py, .ts, .tsx, .js, .jsx)
  - Chunks each file into 50-line blocks
  - Uploads chunks to devpulse-codebase-index in Azure AI Search

Requires: pip install gitpython azure-search-documents
"""

import os
import re
import uuid
import tempfile
import shutil
from pathlib import Path
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    GITHUB_TOKEN, DEFAULT_REPO,
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_CODE_INDEX,
)

# Source file extensions to index
INDEXED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".rb"}
CHUNK_SIZE = 50       # Lines per chunk
BATCH_SIZE = 50       # Azure Search upload batch size
MAX_FILES = 500       # Cap to avoid indexing massive repos entirely


def get_search_client() -> SearchClient:
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_CODE_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".java": "java", ".rs": "rust", ".rb": "ruby",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "unknown")


def extract_function_name(lines: list[str], language: str) -> str:
    """Best-effort: extract the first function/class name visible in the chunk."""
    patterns = {
        "python":     r"^\s*(?:def|class)\s+(\w+)",
        "typescript": r"^\s*(?:function|class|const\s+\w+\s*=\s*(?:async\s+)?(?:\(|function))\s*(\w+)?",
        "javascript": r"^\s*(?:function|class|const\s+\w+\s*=\s*(?:async\s+)?(?:\(|function))\s*(\w+)?",
    }
    pattern = patterns.get(language)
    if pattern:
        for line in lines:
            m = re.search(pattern, line)
            if m:
                return m.group(1) or ""
    return ""


def chunk_file(file_path: str, repo_name: str) -> list[dict]:
    """Splits a source file into CHUNK_SIZE-line chunks, returns index documents."""
    language = detect_language(file_path)
    rel_path = file_path  # already relative after clone walk

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
    except Exception:
        return []

    chunks = []
    for start in range(0, len(all_lines), CHUNK_SIZE):
        chunk_lines = all_lines[start:start + CHUNK_SIZE]
        snippet = "".join(chunk_lines).strip()
        if not snippet:
            continue

        fn_name = extract_function_name(chunk_lines, language)
        chunks.append({
            "id":            str(uuid.uuid4()),
            "file_path":     rel_path,
            "line_number":   start + 1,
            "function_name": fn_name,
            "snippet":       snippet[:1000],
            "content":       snippet[:2000],
            "language":      language,
            "repo":          repo_name,
        })
    return chunks


def clone_repo(repo: str, target_dir: str):
    """Clones the GitHub repo into target_dir using git CLI (no dependency on gitpython)."""
    import subprocess
    clone_url = f"https://github.com/{repo}.git"
    if GITHUB_TOKEN:
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{repo}.git"

    print(f"  Cloning {repo} → {target_dir} ...")
    result = subprocess.run(
        ["git", "clone", "--depth=1", clone_url, target_dir],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr}")
    print(f"  ✅ Clone complete.")


def walk_source_files(root_dir: str) -> list[str]:
    """Walks directory and returns paths of indexable source files."""
    source_files = []
    skip_dirs = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", "venv", ".venv"}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Prune skip directories in-place
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if Path(fname).suffix.lower() in INDEXED_EXTENSIONS:
                source_files.append(os.path.join(dirpath, fname))
                if len(source_files) >= MAX_FILES:
                    return source_files
    return source_files


def main():
    print("=== DevPulse: Codebase Indexer ===")
    print(f"Target repo: {DEFAULT_REPO}")

    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY not set. Aborting.")
        return

    # Clone into a temp directory
    tmp_dir = tempfile.mkdtemp(prefix="devpulse_repo_")
    repo_name = DEFAULT_REPO.replace("/", "__")

    try:
        clone_repo(DEFAULT_REPO, tmp_dir)

        # Walk and chunk
        source_files = walk_source_files(tmp_dir)
        print(f"\n  Found {len(source_files)} source files to index.")

        all_docs = []
        for fp in source_files:
            rel = os.path.relpath(fp, tmp_dir)
            chunks = chunk_file(fp, repo_name)
            # Store relative path in the index, not the temp absolute path
            for c in chunks:
                c["file_path"] = rel
            all_docs.extend(chunks)

        print(f"  Total chunks to upload: {len(all_docs)}")

        # Upload in batches
        client = get_search_client()
        for i in range(0, len(all_docs), BATCH_SIZE):
            batch = all_docs[i:i + BATCH_SIZE]
            result = client.upload_documents(documents=batch)
            succeeded = sum(1 for r in result if r.succeeded)
            print(f"  Batch {i // BATCH_SIZE + 1}: {succeeded}/{len(batch)} succeeded.")

        print(f"\n  ✅ Codebase indexing complete. {len(all_docs)} chunks uploaded.")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"  Temp directory cleaned up.")

    print("\n=== Done. Next: python3 -m main  (to start the FastAPI server) ===")


if __name__ == "__main__":
    main()
