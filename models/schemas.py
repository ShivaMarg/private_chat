from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ── User ───────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username:   str
    password:   str
    public_key: str

class UserOut(BaseModel):
    id:         str
    username:   str
    public_key: str

# ── Channel ────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    name:     str
    is_group: bool = False

class ChannelOut(BaseModel):
    id:          str
    name:        str
    is_group:    bool
    invite_code: str
    members:     List[str]
    created_at:  datetime

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}

# ── Message ────────────────────────────────────────────────────────
class MessageCreate(BaseModel):
    channel_id:           str
    ciphertext:           str
    iv:                   str
    ephemeral_public_key: str
    media_type:           str = "text"
    reply_to:             Optional[str] = None

class MessageOut(BaseModel):
    id:                   str
    channel_id:           str
    sender_id:            str
    sender_username:      str
    ciphertext:           str
    iv:                   str
    ephemeral_public_key: str
    media_type:           str
    starred:              bool
    reply_to:             Optional[str]
    created_at:           datetime

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}

class StarRequest(BaseModel):
    message_id: str
    starred:    bool