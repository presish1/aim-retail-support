"""Bounded local image evidence. Opaque URLs are capabilities in this classroom demo."""
import asyncio
import io
import secrets
import warnings
from pathlib import Path

from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from .reads import SourceError
from .service import iso_now
from .whatsapp import WhatsAppChannel


def register(app, get_store, get_workflow, get_hub):
    @app.post("/api/whatsapp/photo")
    async def upload_photo(request: Request, x_demo_session: str = Header(default="")):
        store, hub = get_store(), get_hub()
        async with hub.locks.setdefault(x_demo_session, asyncio.Lock()):
            channel = store.channel(x_demo_session)
            session = store.session(x_demo_session)
            if not channel or not session or not session["customer"]:
                raise HTTPException(401, "Connect your customer account first.")
            draft = channel.get("return_draft")
            if not draft or draft["step"] != "photos":
                raise HTTPException(409, "Start a return and reach the photo step before attaching evidence.")
            if len(draft["photos"]) >= 3:
                raise HTTPException(422, "Up to 3 photos can be attached to this request.")
            if request.headers.get("content-type", "").split(";")[0] not in ("image/jpeg", "image/png", "image/webp"):
                raise HTTPException(415, "Choose a JPEG, PNG or WebP photo.")
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 5 * 1024 * 1024:
                    raise HTTPException(413, "Choose a photo smaller than 5 MB.")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    original = Image.open(io.BytesIO(data))
                    if original.format not in ("JPEG", "PNG", "WEBP") or original.width * original.height > 20_000_000:
                        raise ValueError()
                    original.load()
                    clean = ImageOps.exif_transpose(original).convert("RGB")
                    clean.thumbnail((1600, 1600))
                    encoded = io.BytesIO()
                    clean.save(encoded, format="JPEG", quality=88)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
                raise HTTPException(422, "That file could not be read as a supported photo.")
            try:
                get_workflow().read_order(session["customer"], draft["order_id"])
            except SourceError as exc:
                raise HTTPException(503, exc.message)
            token = secrets.token_urlsafe(32)
            folder = Path(store.path).parent / "return-photos"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (token + ".jpg")
            path.write_bytes(encoded.getvalue())
            with store.connect() as db:
                db.execute("INSERT INTO media VALUES (?,?,?)", (token, channel["id"], str(path)))
            media = {"id": token, "url": "/api/media/" + token, "received_at": iso_now()}
            draft["photos"].append(media)
            user = {"id": "photo-" + token, "role": "user", "text": "Photo", "at": iso_now(), "media": media, "handled": True}
            reply = WhatsAppChannel.bot_message(f"Photo received ({len(draft['photos'])}/3). You can add another image or continue. Staff will check the item and tag; I haven't assessed the photo.", actions=[{"label": "Continue", "text": "Continue with photos"}])
            channel["messages"].extend([user, reply])
            store.save_channel(channel)
            await hub.emit(channel["id"], WhatsAppChannel(store, get_workflow(), hub).snapshot(channel))
            await hub.studio_changed("conversations", channel.get("reference"))
            return {"ok": True, "media": media}

    @app.get("/api/media/{token}")
    def read_photo(token: str):
        with get_store().connect() as db:
            row = db.execute("SELECT path FROM media WHERE id=?", (token,)).fetchone()
        if not row or not Path(row[0]).is_file():
            raise HTTPException(404, "Photo not found.")
        return FileResponse(row[0], media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
