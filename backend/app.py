"""Local classroom prototype. Simulated identity is deliberately not production auth."""
import asyncio
import secrets
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .model import ModelAdapter
from .service import SourceError, Workflow
from .store import ROOT, Store
from .whatsapp import ChannelHub, WhatsAppChannel
from . import erp, media


app = FastAPI(title="Threadline synthetic support API", version="0.8.0")
store = Store()
adapter = ModelAdapter()
workflow = Workflow(store, adapter)
admin_key = secrets.token_urlsafe(32)
session_locks = {}
channel_hub = ChannelHub()


@app.websocket("/api/studio/ws")
async def studio_socket(socket: WebSocket):
    if urlparse(socket.headers.get("origin", "")).hostname not in ("localhost", "127.0.0.1", "::1"):
        await socket.close(code=1008)
        return
    await socket.accept()
    try:
        hello = await asyncio.wait_for(socket.receive_json(), 10)
        if not isinstance(hello, dict) or not secrets.compare_digest(str(hello.get("key", "")), admin_key):
            await socket.close(code=1008)
            return
        channel_hub.admin_connections.add(socket)
        await socket.send_json({"type": "ready"})
        while True:
            await socket.receive_text()
    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, ValueError):
        pass
    finally:
        channel_hub.admin_connections.discard(socket)


@app.websocket("/api/whatsapp/ws")
async def whatsapp_socket(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    if not origin or urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
        await socket.close(code=1008)
        return
    await socket.accept()
    channel = WhatsAppChannel(store, workflow, channel_hub)
    session_id = None
    try:
        hello = await asyncio.wait_for(socket.receive_json(), timeout=10)
        if not isinstance(hello, dict) or hello.get("type") != "resume":
            await socket.close(code=1008)
            return
        token = hello.get("session_id")
        if token is not None and (not isinstance(token, str) or len(token) > 120):
            await socket.close(code=1008)
            return
        record = channel.start(token)
        session_id = record["id"]
        channel_hub.add(session_id, socket)
        await socket.send_json(channel.snapshot(record))
        await channel_hub.studio_changed("conversations", record.get("reference"))
        while True:
            event = await socket.receive_json()
            if not isinstance(event, dict):
                await socket.send_json({"type": "error", "message": "Send a valid message."})
                continue
            if event.get("type") == "message":
                text, client_id = event.get("text"), event.get("id")
                if not isinstance(text, str) or not text.strip() or len(text) > 2000 or not isinstance(client_id, str) or not 8 <= len(client_id) <= 80:
                    await socket.send_json({"type": "error", "message": "Message must contain 1–2,000 characters and a valid request ID."})
                    continue
                mode = event.get("mode", store.setting("inference_mode") or "model")
                if mode not in ("model", "baseline"):
                    await socket.send_json({"type": "error", "message": "Unknown request mode."})
                    continue
                await channel.handle(session_id, client_id, text.strip(), mode)
            elif event.get("type") == "reset":
                channel_hub.remove(session_id, socket)
                record = channel.start()
                session_id = record["id"]
                channel_hub.add(session_id, socket)
                await socket.send_json(channel.snapshot(record))
                await channel_hub.studio_changed("conversations", record.get("reference"))
            elif event.get("type") == "ping":
                await socket.send_json({"type": "pong"})
            else:
                await socket.send_json({"type": "error", "message": "Unknown channel event."})
    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, ValueError):
        pass
    finally:
        if session_id:
            channel_hub.remove(session_id, socket)


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


@app.get("/api/studio/whatsapp")
def whatsapp_demo_inbox(x_demo_session: str = Header(default=""), _=Depends(require_admin)):
    record = store.channel(x_demo_session)
    if not record:
        raise HTTPException(404, "No active channel session.")
    return WhatsAppChannel(store, workflow, channel_hub).demo_inbox(record)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionBody(StrictBody):
    persona: Literal["a", "b", "guest"] = "a"


class ChatBody(StrictBody):
    message: str = Field(min_length=1, max_length=2000)
    mode: Literal["model", "baseline"] = "model"


class Controls(StrictBody):
    order_api_available: bool | None = None
    feed_health: Literal["healthy", "lagging"] | None = None
    ticket_store_available: bool | None = None
    verification_mode: Literal["demo_match", "code"] | None = None
    inference_mode: Literal["model", "baseline"] | None = None


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
    try:
        return [{"order_id": o["order_id"], "status": o["status"], "items": [{"item_id": i["item_id"], "name": i["name"]} for i in o["items"]]} for o in workflow.reads.list_orders(session["customer"])]
    except SourceError as exc:
        raise HTTPException(503, {"code": exc.code, "message": exc.message})


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
    return erp.state(store)


@app.patch("/api/studio/orders/{order_id}", dependencies=[Depends(require_admin)])
async def update_order(order_id: str, body: erp.OrderPatch):
    return await erp.update_order(store, workflow, channel_hub, order_id, body)


@app.patch("/api/studio/controls", dependencies=[Depends(require_admin)])
async def controls(body: Controls):
    for key, value in body.model_dump(exclude_none=True).items():
        store.set_setting(key, value)
    store.log("settings", "workspace", "updated", "Workspace settings updated", body.model_dump(exclude_none=True))
    await channel_hub.source_changed(store)
    return {"settings": store.settings()}


@app.post("/api/studio/reset", dependencies=[Depends(require_admin)])
async def reset():
    store.reset()
    for session_id in list(channel_hub.connections):
        await channel_hub.emit(session_id, {"type": "reset_required"})
    store.log("workspace", "samples", "restored", "Sample data restored")
    await channel_hub.studio_changed()
    return {"ok": True, "demo_now": store.setting("demo_now")}


erp.register(app, lambda: store, lambda: workflow, lambda: channel_hub, require_admin)
media.register(app, lambda: store, lambda: workflow, lambda: channel_hub)

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
