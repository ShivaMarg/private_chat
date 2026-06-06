from fastapi import APIRouter, HTTPException, status
from core.database import get_db
from core.security import hash_password, verify_password, create_token
from models.schemas import UserCreate, UserOut
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/register", response_model=dict)
async def register(body: UserCreate):
    db = get_db()
    if await db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=400, detail="Username taken")

    doc = {
        "username":   body.username,
        "password":   hash_password(body.password),
        "public_key": body.public_key,   # ECDH pub key from client
        "created_at": datetime.utcnow(),
    }
    result = await db.users.insert_one(doc)
    token  = create_token(str(result.inserted_id))
    return {"token": token, "user_id": str(result.inserted_id), "username": body.username}

@router.post("/login", response_model=dict)
async def login(body: UserCreate):
    db   = get_db()
    user = await db.users.find_one({"username": body.username})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(str(user["_id"]))
    return {
        "token":      token,
        "user_id":    str(user["_id"]),
        "username":   user["username"],
        "public_key": user["public_key"],
    }

@router.get("/user/{username}", response_model=UserOut)
async def get_user(username: str):
    """Public endpoint — returns only username + public key (needed for key exchange)"""
    db   = get_db()
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=str(user["_id"]), username=user["username"], public_key=user["public_key"])
