from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from core.database import get_db
from core.security import decode_token
from bson import ObjectId
from datetime import datetime
import json

router = APIRouter()

# In-memory room registry: { channel_id: { user_id: WebSocket } }
rooms: dict[str, dict[str, WebSocket]] = {}

async def _get_username(db, user_id: str) -> str:
    user = await db.users.find_one({"_id": ObjectId(user_id)}, {"username": 1})
    return user["username"] if user else "unknown"

@router.websocket("/chat/{channel_id}")
async def ws_chat(
    websocket: WebSocket,
    channel_id: str,
    token: str = Query(...)     # ?token=<jwt>  passed in URL
):
    # ── auth ──────────────────────────────────────────────────────
    user_id = decode_token(token)
    db      = get_db()

    ch = await db.channels.find_one({"_id": ObjectId(channel_id)})
    if not ch or ObjectId(user_id) not in ch.get("members", []):
        await websocket.close(code=4003)
        return

    await websocket.accept()
    username = await _get_username(db, user_id)

    # ── join room ─────────────────────────────────────────────────
    if channel_id not in rooms:
        rooms[channel_id] = {}
    rooms[channel_id][user_id] = websocket

    # notify others that this user is online
    await _broadcast(channel_id, user_id, {
        "type":     "presence",
        "user_id":  user_id,
        "username": username,
        "online":   True,
    })

    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)

            # ── handle incoming message ───────────────────────────
            if data.get("type") == "message":
                doc = {
                    "channel_id":           ObjectId(channel_id),
                    "sender_id":            ObjectId(user_id),
                    "ciphertext":           data["ciphertext"],
                    "iv":                   data["iv"],
                    "ephemeral_public_key": data["ephemeral_public_key"],
                    "media_type":           data.get("media_type", "text"),
                    "reply_to":             ObjectId(data["reply_to"]) if data.get("reply_to") else None,
                    "starred":              False,
                    "created_at":           datetime.utcnow(),
                }
                result = await db.messages.insert_one(doc)
                msg_id = str(result.inserted_id)

                # broadcast to everyone in room (including sender for receipt confirmation)
                await _broadcast(channel_id, None, {
                    "type":                 "message",
                    "id":                   msg_id,
                    "channel_id":           channel_id,
                    "sender_id":            user_id,
                    "sender_username":      username,
                    "ciphertext":           data["ciphertext"],
                    "iv":                   data["iv"],
                    "ephemeral_public_key": data["ephemeral_public_key"],
                    "media_type":           data.get("media_type", "text"),
                    "reply_to":             data.get("reply_to"),
                    "starred":              False,
                    "created_at":           datetime.utcnow().isoformat(),
                })

            # ── typing indicator ──────────────────────────────────
            elif data.get("type") == "typing":
                await _broadcast(channel_id, user_id, {
                    "type":     "typing",
                    "user_id":  user_id,
                    "username": username,
                    "typing":   data.get("typing", True),
                })

            # ── read receipt ──────────────────────────────────────
            elif data.get("type") == "read":
                await _broadcast(channel_id, user_id, {
                    "type":       "read",
                    "user_id":    user_id,
                    "message_id": data.get("message_id"),
                })

    except WebSocketDisconnect:
        rooms[channel_id].pop(user_id, None)
        if not rooms[channel_id]:
            del rooms[channel_id]

        await _broadcast(channel_id, user_id, {
            "type":     "presence",
            "user_id":  user_id,
            "username": username,
            "online":   False,
        })

async def _broadcast(channel_id: str, skip_user_id: str | None, payload: dict):
    """Send payload to all connections in a room, optionally skipping one user."""
    room = rooms.get(channel_id, {})
    dead = []
    for uid, ws in room.items():
        if uid == skip_user_id:
            continue
        try:
            await ws.send_text(json.dumps(payload, default=str))
        except Exception:
            dead.append(uid)
    for uid in dead:
        room.pop(uid, None)
