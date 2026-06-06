from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

# ── helpers ────────────────────────────────────────────────────────
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    @classmethod
    def __get_pydantic_json_schema__(cls, schema):
        schema.update(type="string")
        return schema

# ── User ───────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username:   str
    password:   str
    public_key: str   # ECDH public key as JWK JSON string (generated client-side)

class UserOut(BaseModel):
    id:         str
    username:   str
    public_key: str

# ── Channel ────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    name:     str
    is_group: bool = False   # False = 1:1 DM, True = group room

class ChannelOut(BaseModel):
    id:          str
    name:        str
    is_group:    bool
    invite_code: str
    members:     List[str]
    created_at:  datetime

# ── Message ────────────────────────────────────────────────────────
# The server NEVER sees plaintext. 
# `ciphertext` is a base64 string of the AES-GCM encrypted message.
# `iv` is the initialisation vector (base64), required for decryption.
# `ephemeral_public_key` carries the sender's one-time ECDH pub key
#   so the recipient can derive the shared AES key.
class MessageCreate(BaseModel):
    channel_id:          str
    ciphertext:          str          # base64(AES-GCM encrypted content)
    iv:                  str          # base64(12-byte IV)
    ephemeral_public_key: str         # base64 JWK — one-time sender key
    media_type:          str = "text" # text | image | sticker | file
    reply_to:            Optional[str] = None  # message_id being replied to

class MessageOut(BaseModel):
    id:                  str
    channel_id:          str
    sender_id:           str
    sender_username:     str
    ciphertext:          str
    iv:                  str
    ephemeral_public_key: str
    media_type:          str
    starred:             bool
    reply_to:            Optional[str]
    created_at:          datetime

class StarRequest(BaseModel):
    message_id: str
    starred:    bool
