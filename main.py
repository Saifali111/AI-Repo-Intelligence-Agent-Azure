"""
DevPulse FastAPI Server
Serves the Web Chat UI and exposes the 2-agent pipeline via REST API.

Run:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import os
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from agents.agent_graph import run_devpulse_pipeline

if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor(
        connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    )

app = FastAPI(
    title="DevPulse Maintainer Copilot",
    description="AI copilot for open-source maintainers — powered by Azure AI Foundry.",
    version="1.0.0",
)

FastAPIInstrumentor.instrument_app(app)

# Mount static files (Web Chat UI)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None   # Pass back the same ID for multi-turn


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    evaluation: dict
    retries_used: int


class IngestRequest(BaseModel):
    repo: str | None = None   # Defaults to DEFAULT_REPO in settings if omitted


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the Web Chat UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "DevPulse API is running. UI not found — add static/index.html."}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "DevPulse Maintainer Copilot"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint.
    Accepts a user query and optional conversation_id for multi-turn conversations.
    Returns the 3-part structured response after critic validation.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        result = run_devpulse_pipeline(
            user_input=req.query.strip(),
            conversation_id=req.conversation_id,
        )
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            evaluation=result["evaluation"],
            retries_used=result["retries_used"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/ingest")
async def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger codebase re-indexing in the background.
    Optionally pass a custom repo (defaults to DEFAULT_REPO in settings).
    """
    from config.settings import DEFAULT_REPO
    target_repo = req.repo or DEFAULT_REPO

    def run_ingestion(repo: str):
        from scripts.repo_indexer import main as run_indexer
        from scripts.ingest_history import main as run_history
        print(f"[Ingest] Starting background ingestion for '{repo}'...")
        run_history()
        run_indexer()
        print(f"[Ingest] Background ingestion complete for '{repo}'.")

    background_tasks.add_task(run_ingestion, target_repo)
    return {
        "status": "accepted",
        "message": f"Ingestion started in background for repo: {target_repo}",
    }


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
