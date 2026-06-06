from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from core.database import connect_db, disconnect_db
from routers import auth, messages, channels, websocket

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await disconnect_db()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/api/auth",     tags=["auth"])
app.include_router(channels.router,  prefix="/api/channels", tags=["channels"])
app.include_router(messages.router,  prefix="/api/messages", tags=["messages"])
app.include_router(websocket.router, prefix="/ws",           tags=["ws"])

# Static files MUST be mounted LAST — it catches all unmatched routes

@app.get("/api/debug/routes")
def list_routes():
    return [{"path": r.path, "methods": list(r.methods)} for r in app.routes]

import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

