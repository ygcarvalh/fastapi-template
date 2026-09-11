from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.request_context import REQUEST_ID_HEADER


# Outermost, so a 401 or a 429 reaches the browser with its headers too.
# No credentials: authentication is a bearer header, and nothing sets a cookie.
def register_cors(app: FastAPI, *, origins: list[str]) -> None:
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
