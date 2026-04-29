import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from . import auth, db, redis_client
from .routes import admin as admin_routes
from .routes import auth as auth_routes
from .routes import documents as documents_routes
from .routes import search as search_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await redis_client.init_redis()
    await auth.ensure_admin_seed()
    try:
        yield
    finally:
        await redis_client.close_redis()
        await db.close_pool()


app = FastAPI(title="ETL API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/metrics", make_asgi_app())
app.include_router(auth_routes.router)
app.include_router(documents_routes.router)
app.include_router(search_routes.router)
app.include_router(admin_routes.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
