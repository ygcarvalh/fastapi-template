from fastapi import APIRouter

from app.api.v1.routes import auth, items, users

api_router = APIRouter()

api_router.include_router(auth.public_router)
api_router.include_router(users.public_router)

api_router.include_router(users.private_router)
api_router.include_router(items.private_router)
