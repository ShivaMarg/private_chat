from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME",   "private_chat")

client: AsyncIOMotorClient = None
db = None

async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # ── indexes ────────────────────────────────────────────────────
    # TTL: messages expire after 3 days UNLESS starred
    # We use a partial index: only documents where starred=False get TTL
    await db.messages.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=259200,   # 3 days
        partialFilterExpression={"starred": False},
        name="ttl_non_starred"
    )
    await db.messages.create_index([("channel_id", ASCENDING), ("created_at", ASCENDING)])
    await db.messages.create_index([("sender_id",  ASCENDING)])

    await db.channels.create_index([("invite_code", ASCENDING)], unique=True)
    await db.channels.create_index([("members",     ASCENDING)])

    await db.users.create_index([("username", ASCENDING)], unique=True)

    print("✅ MongoDB connected & indexes ensured")

async def disconnect_db():
    if client:
        client.close()

def get_db():
    return db
