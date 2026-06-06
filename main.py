from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from core.database import connect_db, disconnect_db
from routers import auth, messages, channels, websocket
import os

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

# ── API routes ────────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/auth",     tags=["auth"])
app.include_router(channels.router,  prefix="/api/channels", tags=["channels"])
app.include_router(messages.router,  prefix="/api/messages", tags=["messages"])
app.include_router(websocket.router, prefix="/ws",           tags=["ws"])

@app.get("/api/debug/routes")
def list_routes():
    return [{"path": r.path, "methods": list(r.methods or [])} for r in app.routes]

# ── Serve static JS files ─────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/js", StaticFiles(directory=os.path.join(static_dir, "js")), name="js")

# ── Catch-all: serve index.html for everything else ───────────────
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    return FileResponse(os.path.join(static_dir, "index.html"))