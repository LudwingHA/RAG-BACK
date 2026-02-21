# from fastapi import APIRouter
# from app.db.db import get_db
# router = APIRouter()
# def health_check():
#     try:
#         db = get_db()
#         db.command("ping")
#         return {"status":"MongoDB Connect Success"}
#     except Exception as e:
#         return {"status":"error", "details": e}