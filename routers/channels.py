from fastapi import APIRouter, Depends, HTTPException
from core.database import get_db
from core.security import get_current_user
from models.schemas import ChannelCreate, ChannelOut
from bson import ObjectId
from datetime import datetime
import secrets
import string

router = APIRouter()

def _make_invite() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(10))

def _fmt(ch: dict) -> dict:
    return {
        "id":          str(ch["_id"]),
        "name":        ch["name"],
        "is_group":    ch.get("is_group", False),
        "invite_code": ch["invite_code"],
        "members":     [str(m) for m in ch.get("members", [])],
        "created_at":  ch["created_at"],
    }

@router.post("/", response_model=ChannelOut)
async def create_channel(body: ChannelCreate, user_id: str = Depends(get_current_user)):
    db  = get_db()
    doc = {
        "name":        body.name,
        "is_group":    body.is_group,
        "invite_code": _make_invite(),
        "members":     [ObjectId(user_id)],
        "created_at":  datetime.utcnow(),
    }
    result = await db.channels.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _fmt(doc)

@router.post("/join/{invite_code}", response_model=ChannelOut)
async def join_channel(invite_code: str, user_id: str = Depends(get_current_user)):
    db  = get_db()
    oid = ObjectId(user_id)
    ch  = await db.channels.find_one({"invite_code": invite_code})
    if not ch:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    if oid not in ch.get("members", []):
        await db.channels.update_one(
            {"_id": ch["_id"]},
            {"$addToSet": {"members": oid}}
        )
        ch["members"].append(oid)
    return _fmt(ch)

@router.get("/", response_model=list)
async def list_my_channels(user_id: str = Depends(get_current_user)):
    db  = get_db()
    oid = ObjectId(user_id)
    channels = await db.channels.find({"members": oid}).to_list(100)
    return [_fmt(c) for c in channels]

@router.delete("/{channel_id}")
async def leave_channel(channel_id: str, user_id: str = Depends(get_current_user)):
    db  = get_db()
    oid = ObjectId(user_id)
    await db.channels.update_one(
        {"_id": ObjectId(channel_id)},
        {"$pull": {"members": oid}}
    )
    return {"ok": True}
