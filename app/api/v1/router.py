from fastapi import APIRouter

from app.api.v1.routes import auth, items, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(items.router)
