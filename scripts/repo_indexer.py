"""
Step 3: Clone a GitHub repo and index source code into devpulse-codebase-index
using Tree-sitter AST parsing (capturing classes, methods, functions, callers, and imports).

Run:
    python3 -m scripts.repo_indexer
"""

import os
import uuid
import tempfile
import shutil
import time
from pathlib import Path
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

from config.settings import (
    GITHUB_TOKEN, DEFAULT_REPO,
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_CODE_INDEX,
)

INDEXED_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py"}
BATCH_SIZE = 50
MAX_FILES = 1000


def get_search_client() -> SearchClient:
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_CODE_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


# ─────────────────────────────────────────────────────────
# Tree-sitter AST Parsing Engine
# ─────────────────────────────────────────────────────────

def get_ast_parser(language: str):
    """Initializes Tree-sitter parser for TypeScript, JavaScript, or Python."""
    try:
        from tree_sitter_languages import get_parser
        parser_name = "tsx" if language in ("typescript", "tsx") else language
        return get_parser(parser_name)
    except Exception as e:
        print(f"[AST] Warning: Tree-sitter parser unavailable for '{language}': {e}")
        return None


def extract_calls_from_node(node, source_bytes: bytes) -> set[str]:
    """Recursively extracts function/method names invoked inside a node."""
    calls = set()
    if node.type in ("call_expression", "call"):
        for child in node.children:
            if child.type in ("identifier", "property_identifier"):
                calls.add(source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore"))
    for child in node.children:
        calls.update(extract_calls_from_node(child, source_bytes))
    return calls


def parse_file_with_ast(file_path: str, repo_name: str) -> list[dict]:
    """
    Parses a source file into logical AST units (Classes, Functions, Methods)
    with parent class context, line numbers, called functions, and imports.
    """
    ext = Path(file_path).suffix.lower()
    lang_map = {
        ".ts": "typescript", ".tsx": "tsx",
        ".js": "javascript", ".jsx": "javascript",
        ".py": "python"
    }
    language = lang_map.get(ext)
    if not language:
        return []

    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
    except Exception:
        return []

    parser = get_ast_parser(language)
    if not parser:
        return []

    tree = parser.parse(source_bytes)
    root = tree.root_node

    # 1. Collect all top-level imports in the file
    imports = []
    for child in root.children:
        if child.type in ("import_statement", "import_from_statement", "import_declaration"):
            imports.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore").strip())
    imports_str = "\n".join(imports[:15])

    chunks = []

    def visit_node(node, current_class=""):
        node_type = node.type

        # Track Class Definition
        if node_type in ("class_declaration", "class_definition"):
            class_name = ""
            for c in node.children:
                if c.type in ("identifier", "type_identifier"):
                    class_name = source_bytes[c.start_byte:c.end_byte].decode("utf-8", errors="ignore")
                    break
            
            # Recurse into class children with parent class tracked
            for c in node.children:
                visit_node(c, current_class=class_name or current_class)
            return

        # Track Function / Method Definition
        is_function = node_type in (
            "function_declaration", "method_definition", "function_definition",
            "arrow_function", "generator_function_declaration"
        )

        if is_function:
            fn_name = ""
            # Extract function/method name
            for c in node.children:
                if c.type in ("identifier", "property_identifier"):
                    fn_name = source_bytes[c.start_byte:c.end_byte].decode("utf-8", errors="ignore")
                    break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            snippet = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore").strip()

            # Extract called functions inside this function
            called_fns = list(extract_calls_from_node(node, source_bytes))[:10]
            called_fns_str = ", ".join(called_fns)

            # Build rich searchable context header
            hierarchy = f"[File: {file_path}]"
            if current_class:
                hierarchy += f" [Class: {current_class}]"
            if fn_name:
                hierarchy += f" [Function: {fn_name}]"

            content = f"{hierarchy}\n\n{snippet[:2000]}"

            chunks.append({
                "id": str(uuid.uuid4()),
                "file_path": file_path,
                "line_number": start_line,
                "end_line": end_line,
                "parent_class": current_class,
                "function_name": fn_name,
                "called_functions": called_fns_str,
                "imports": imports_str,
                "snippet": snippet[:1000],
                "content": content,
                "language": language,
                "repo": repo_name,
            })
            return

        # Recurse into other nodes
        for c in node.children:
            visit_node(c, current_class)

    visit_node(root)
    return chunks


# ─────────────────────────────────────────────────────────
# Git Clone & Indexing Pipeline
# ─────────────────────────────────────────────────────────

def clone_repo(repo: str, target_dir: str):
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
    source_files = []
    # Skip test/example clutter so we index the ACTUAL core codebase
    skip_dirs = {
        "node_modules", ".git", "__pycache__", ".next", "dist", "build", 
        "venv", ".venv", "examples", "test", "tests", "docs", "fixtures", 
        "bench", ".github", "apps", "evals"
    }
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if Path(fname).suffix.lower() in INDEXED_EXTENSIONS:
                source_files.append(os.path.join(dirpath, fname))
                if len(source_files) >= MAX_FILES:
                    return source_files
    return source_files


def main():
    print("=== DevPulse: AST Codebase Indexer (Tree-sitter) ===")
    print(f"Target repo: {DEFAULT_REPO}")

    if not AZURE_SEARCH_KEY:
        print("ERROR: AZURE_SEARCH_KEY not set. Aborting.")
        return

    tmp_dir = tempfile.mkdtemp(prefix="devpulse_ast_")
    repo_name = DEFAULT_REPO.replace("/", "__")

    try:
        clone_repo(DEFAULT_REPO, tmp_dir)
        source_files = walk_source_files(tmp_dir)
        print(f"\n  Found {len(source_files)} source files to index with AST.")

        all_docs = []
        for fp in source_files:
            rel = os.path.relpath(fp, tmp_dir)
            chunks = parse_file_with_ast(fp, repo_name)
            for c in chunks:
                c["file_path"] = rel
            all_docs.extend(chunks)

        print(f"  Generated {len(all_docs)} AST semantic code units.")

        # Upload in batches
        client = get_search_client()
        for i in range(0, len(all_docs), BATCH_SIZE):
            batch = all_docs[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    result = client.upload_documents(documents=batch)
                    succeeded = sum(1 for r in result if r.succeeded)
                    print(f"  Batch {batch_num}: {succeeded}/{len(batch)} uploaded.")
                    time.sleep(0.6)  # Steady pace for Free Tier
                    break
                except Exception as upload_err:
                    err_msg = str(upload_err).lower()
                    if "too many requests" in err_msg or "429" in err_msg:
                        wait_seconds = (attempt + 1) * 3
                        print(f"  ⚠️ Rate-limited on Batch {batch_num}. Waiting {wait_seconds}s before retry ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_seconds)
                    else:
                        print(f"  ❌ Batch {batch_num} error: {upload_err}")
                        break

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("  Temp directory cleaned up.")

    print("\n=== Done! Codebase is now indexed with full AST hierarchy. ===")


if __name__ == "__main__":
    main()
