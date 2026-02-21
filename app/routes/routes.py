from fastapi import APIRouter
from app.routes import user
routes = APIRouter()
routes.include_router(user.router, prefix="/user")
