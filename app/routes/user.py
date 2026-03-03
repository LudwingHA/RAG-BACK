from fastapi import APIRouter, HTTPException
from app.models.userModel import UserCreate, LoginRequest
from app.services.user_services import UserService
from app.utils.auth_utils import create_access_token
router = APIRouter()
user_service = UserService()

@router.post("/api/auth/register")
async def register(user: UserCreate):
    new_user = user_service.create_user(user)
    if not new_user:
        raise HTTPException(status_code=400,
                             detail="El correo ya existe en la SICT"
                             )
    return {"status": "success", "user": new_user}


@router.post("/api/auth/login")
async def login(login_data: LoginRequest):

    user = user_service.authenticate_user(
        login_data.email,
        login_data.password
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas"
        )

    access_token = create_access_token(
        data={"sub": str(user["_id"])}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "_id": str(user["_id"]),
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "role": user["role"],
            "cargo": user["cargo"],
            "email": user["email"],
            "created_at": user["created_at"]

        }
    }
