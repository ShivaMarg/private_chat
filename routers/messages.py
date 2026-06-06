from fastapi import APIRouter, Depends, HTTPException, Query
from core.database import get_db
from core.security import get_current_user
from models.schemas import MessageCreate, MessageOut, StarRequest
from bson import ObjectId
from datetime import datetime

router = APIRouter()

async def _require_member(db, channel_id: str, user_id: str):
    ch = await db.channels.find_one({"_id": ObjectId(channel_id)})
    if not ch or ObjectId(user_id) not in ch.get("members", []):
        raise HTTPException(status_code=403, detail="Not a channel member")
    return ch

async def _fmt(db, msg: dict) -> dict:
    user = await db.users.find_one({"_id": msg["sender_id"]}, {"username": 1})
    return {
        "id":                   str(msg["_id"]),
        "channel_id":           str(msg["channel_id"]),
        "sender_id":            str(msg["sender_id"]),
        "sender_username":      user["username"] if user else "unknown",
        "ciphertext":           msg["ciphertext"],
        "iv":                   msg["iv"],
        "ephemeral_public_key": msg["ephemeral_public_key"],
        "media_type":           msg.get("media_type", "text"),
        "starred":              msg.get("starred", False),
        "reply_to":             str(msg["reply_to"]) if msg.get("reply_to") else None,
        "created_at":           msg["created_at"],
    }

@router.get("/{channel_id}", response_model=list)
async def get_history(
    channel_id: str,
    limit:  int = Query(50, le=200),
    before: str = Query(None),   # message_id cursor for pagination
    user_id: str = Depends(get_current_user)
):
    db = get_db()
    await _require_member(db, channel_id, user_id)

    query: dict = {"channel_id": ObjectId(channel_id)}
    if before:
        query["_id"] = {"$lt": ObjectId(before)}

    msgs = await db.messages.find(query).sort("_id", -1).limit(limit).to_list(limit)
    msgs.reverse()
    return [await _fmt(db, m) for m in msgs]

@router.get("/{channel_id}/starred", response_model=list)
async def get_starred(channel_id: str, user_id: str = Depends(get_current_user)):
    db = get_db()
    await _require_member(db, channel_id, user_id)
    msgs = await db.messages.find(
        {"channel_id": ObjectId(channel_id), "starred": True}
    ).sort("created_at", 1).to_list(500)
    return [await _fmt(db, m) for m in msgs]

@router.patch("/star", response_model=dict)
async def toggle_star(body: StarRequest, user_id: str = Depends(get_current_user)):
    db  = get_db()
    msg = await db.messages.find_one({"_id": ObjectId(body.message_id)})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    await _require_member(db, str(msg["channel_id"]), user_id)

    # When starring: also remove the TTL index field so it never expires
    update = {"$set": {"starred": body.starred}}
    await db.messages.update_one({"_id": ObjectId(body.message_id)}, update)
    return {"ok": True, "starred": body.starred}

@router.delete("/{message_id}")
async def delete_message(message_id: str, user_id: str = Depends(get_current_user)):
    db  = get_db()
    msg = await db.messages.find_one({"_id": ObjectId(message_id)})
    if not msg:
        raise HTTPException(status_code=404, detail="Not found")
    if str(msg["sender_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Can only delete your own messages")
    await db.messages.delete_one({"_id": ObjectId(message_id)})
    return {"ok": True}
