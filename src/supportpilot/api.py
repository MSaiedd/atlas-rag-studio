"""Authenticated support API; refund effects are sandbox ledger writes only."""

import os
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Agent
from .security import make_auth
from .store import Conflict, NotFound, Store


class TicketBody(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    order_id: str | None = Field(default=None, min_length=1, max_length=100)


class Decision(BaseModel):
    approve: bool


def create_app(db_path=None, tokens=None, backend=None, agent_factory=Agent):
    auth = make_auth(tokens)
    store = Store(db_path or os.environ.get("DB_PATH", "data/app.db"))
    backend = backend or os.environ.get("AGENT_BACKEND", "baseline")
    if backend not in {"baseline", "ollama"}:
        raise ValueError("AGENT_BACKEND must be baseline or ollama")
    agent = agent_factory(
        store,
        backend,
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"),
    )
    app = FastAPI(title="SupportPilot", version="0.1.0")
    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.exception_handler(NotFound)
    def not_found(request: Request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(Conflict)
    def conflict(request: Request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(PermissionError)
    def forbidden(request: Request, error):
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web / "index.html")

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": backend, "commerce": "sandbox"}

    @app.post("/tickets", status_code=201)
    def create_ticket(body: TicketBody, principal=Depends(auth)):
        ticket_id = store.new_ticket(principal, body.message, body.order_id)
        try:
            answer, trace, status = agent.run(principal, ticket_id, body.message, body.order_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            store.finish(
                principal,
                ticket_id,
                "Provider failed; review any pending request before retrying.",
                [],
                "failed",
            )
            raise HTTPException(
                502, {"message": "Agent provider failed", "ticket_id": ticket_id}
            ) from error
        store.finish(principal, ticket_id, answer, trace, status)
        return store.ticket(principal, ticket_id)

    @app.get("/tickets/{ticket_id}")
    def ticket(ticket_id: str, principal=Depends(auth)):
        return store.ticket(principal, ticket_id)

    @app.get("/refunds")
    def refunds(principal=Depends(auth)):
        return store.pending(principal)

    @app.post("/refunds/{refund_id}/decision")
    def decide(refund_id: str, body: Decision, principal=Depends(auth)):
        return store.decide(principal, refund_id, body.approve)

    @app.get("/audit")
    def audit(principal=Depends(auth)):
        return store.events(principal)

    return app
