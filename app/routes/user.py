from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def getUser():
    return {"status": 200, "content": {
        "name": "Ludwing", "lastName": "Hernandez"
    } }