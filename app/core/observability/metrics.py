from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

METRICS_ENDPOINT = "/metrics"


def register_metrics(app: FastAPI) -> None:
    Instrumentator().instrument(app).expose(app, endpoint=METRICS_ENDPOINT)
