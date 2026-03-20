from fastapi import APIRouter, HTTPException, Depends
from app.models.userModel import UserCreate, LoginRequest, PasswordChange, ProfileUpdate
from app.services.user_services import UserService
from app.utils.auth_utils import create_access_token, get_current_user

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
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "cargo": user["cargo"],
            "role": user["role"],
            "created_at": user["created_at"],
            "last_login": user.get("last_login"),
            "phone": user.get("phone"),
            "extension": user.get("extension"),
            "office": user.get("office"),
            "address": user.get("address"),
            "employee_id": user.get("employee_id"),
            "department": user.get("department"),
            "area": user.get("area"),
            "supervisor": user.get("supervisor"),
            "profile_picture": user.get("profile_picture"),
            "updated_at": user.get("updated_at")

        }
    }
@router.get("/api/profile")
async def get_profile(current_user_id: str = Depends(get_current_user)):
    """
    Obtener el perfil completo del usuario actual
    """
    profile = user_service.get_profile(current_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return profile

@router.put("/api/profile")
async def update_profile(
    profile_data: ProfileUpdate,
    current_user_id: str = Depends(get_current_user)
):
    """
    Actualizar el perfil del usuario actual
    """
    updated_profile = user_service.update_profile(current_user_id, profile_data)
    
    if not updated_profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    
    if "error" in updated_profile:
        raise HTTPException(status_code=400, detail=updated_profile["error"])
    
    return updated_profile

@router.post("/api/profile/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user_id: str = Depends(get_current_user)
):
    """
    Cambiar la contraseña del usuario actual
    """
    result = user_service.change_password(current_user_id, password_data)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result