"""Local classroom prototype. Simulated identity is deliberately not production auth."""
import asyncio
import secrets
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .model import ModelAdapter
from .service import SourceError, Workflow, iso_now
from .store import ROOT, Store


app = FastAPI(title="Threadline synthetic support API", version="0.2.0")
store = Store()
adapter = ModelAdapter()
workflow = Workflow(store, adapter)
admin_key = secrets.token_urlsafe(32)
session_locks = {}


@app.middleware("http")
async def local_origin_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
        if urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Local classroom prototype accepts loopback origins only."}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def require_admin(x_demo_admin: str = Header(default="")):
    if not secrets.compare_digest(x_demo_admin, admin_key):
        raise HTTPException(403, "Demo console capability required.")


def require_session(x_demo_session: str = Header(default="")):
    session = store.session(x_demo_session)
    if not session:
        raise HTTPException(401, "Start a new simulated customer session.")
    return session


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionBody(StrictBody):
    persona: Literal["a", "b", "guest"] = "a"


class ChatBody(StrictBody):
    message: str = Field(min_length=1, max_length=2000)
    mode: Literal["model", "baseline"] = "model"


class OrderUpdate(StrictBody):
    status: Literal["processing", "in_transit", "delivered", "partially_delivered", "cancelled"]
    carrier_eta_date: str | None = None


class Controls(StrictBody):
    order_api_available: bool | None = None
    feed_health: Literal["healthy", "lagging"] | None = None
    ticket_store_available: bool | None = None


@app.get("/api/health")
async def health():
    return {"ok": True, "synthetic": True, "demo_now": store.setting("demo_now"), "model": await adapter.health()}


@app.post("/api/session")
def create_session(body: SessionBody):
    token = secrets.token_urlsafe(24)
    customer = None if body.persona == "guest" else "demo-customer-" + body.persona
    store.new_session(token, customer)
    return {"session_id": token, "customer": customer, "simulated": True}


@app.get("/api/orders")
def my_orders(session=Depends(require_session)):
    if not session["customer"]:
        raise HTTPException(403, "Simulated verification required.")
    if not store.setting("order_api_available"):
        raise HTTPException(503, "Order API unavailable.")
    return [{"order_id": o["order_id"], "status": o["status"], "items": [{"item_id": i["item_id"], "name": i["name"]} for i in o["items"]]} for o in store.orders(session["customer"])]


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, session=Depends(require_session)):
    try:
        return workflow.read_order(session["customer"], order_id)
    except SourceError as exc:
        raise HTTPException(404 if exc.code == "INACCESSIBLE_ORDER" else 503, {"code": exc.code, "message": exc.message})


@app.post("/api/chat")
async def chat(body: ChatBody, session=Depends(require_session)):
    lock = session_locks.setdefault(session["id"], asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "Please wait for your current request to finish.")
    async with lock:
        return await workflow.chat(session["id"], body.message.strip(), body.mode)


@app.get("/api/traces")
def my_traces(session=Depends(require_session)):
    return store.records("traces", session["id"])


@app.get("/api/studio/bootstrap")
def bootstrap():
    # Deliberately obtainable locally: this is an evaluator's synthetic-data studio.
    # Run on loopback only; do not present this capability exchange as real auth.
    return {"admin_key": admin_key, "synthetic": True}


@app.get("/api/studio/state", dependencies=[Depends(require_admin)])
def studio_state():
    return {"orders": store.orders(), "settings": store.settings(), "tickets": store.records("tickets"), "traces": store.records("traces")}


@app.patch("/api/studio/orders/{order_id}", dependencies=[Depends(require_admin)])
def update_order(order_id: str, body: OrderUpdate):
    order = store.order(order_id)
    if not order:
        raise HTTPException(404, "No such synthetic order.")
    if body.carrier_eta_date:
        from datetime import date
        try:
            date.fromisoformat(body.carrier_eta_date)
        except ValueError:
            raise HTTPException(422, "ETA must be an ISO calendar date.")
    order["status"] = body.status
    order["carrier_eta_date"] = body.carrier_eta_date if body.status != "delivered" else None
    order["source_updated_at"] = store.setting("demo_now")
    for item in order["items"]:
        if body.status == "delivered":
            item["status"] = "delivered"
            item["delivered_at"] = item["delivered_at"] or store.setting("demo_now")
        elif body.status in ("in_transit", "processing", "cancelled"):
            item["status"] = body.status
            item["delivered_at"] = None
    store.save_order(order)
    return {"order": order, "saved_at": iso_now(), "source": "SQLite"}


@app.patch("/api/studio/controls", dependencies=[Depends(require_admin)])
def controls(body: Controls):
    for key, value in body.model_dump(exclude_none=True).items():
        store.set_setting(key, value)
    return {"settings": store.settings()}


@app.post("/api/studio/reset", dependencies=[Depends(require_admin)])
def reset():
    store.reset()
    return {"ok": True, "demo_now": store.setting("demo_now")}


dist = ROOT / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(dist / "index.html")
