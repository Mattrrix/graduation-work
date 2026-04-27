import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from . import db, kafka_producer
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await kafka_producer.start()
    try:
        yield
    finally:
        await kafka_producer.stop()
        await db.close_pool()


app = FastAPI(title="ETL Extract", version="0.1.0", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())
app.include_router(router)
