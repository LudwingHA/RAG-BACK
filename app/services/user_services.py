from passlib.context import CryptContext
from app.db.db import db
from app.models.userModel import UserCreate, UserInDB, ProfileUpdate, PasswordChange
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from bson import ObjectId
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

class UserService:
    def __init__(self):
        self.collection = db["users"]

    def hash_password(self, password: str):
        return pwd_context.hash(password)

    def verify_password(self, plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    def create_user(self, user_in: UserCreate):
        email = user_in.email.lower().strip()

        if self.collection.find_one({"email": email}):
            return None

        user_dict = user_in.model_dump()
        user_dict["email"] = email
        user_dict["hashed_password"] = self.hash_password(user_dict.pop("password"))
        user_dict["created_at"] = datetime.utcnow()
        user_dict["is_active"] = True
        user_dict["role"] = "user"

        result = self.collection.insert_one(user_dict)

        user_dict["_id"] = str(result.inserted_id)
        del user_dict["hashed_password"]

        return user_dict
    def get_user_by_email(self, email: str):
        return self.collection.find_one({"email": email})
    def get_user_by_id(self, user_id: str):
        try:
            return self.collection.find_one({"_id": ObjectId(user_id)})
        except:
            return None
    def authenticate_user(self, email: str, password: str):
        user = self.collection.find_one({"email": email})
        if not user:
            return False
        if not self.verify_password(password, user["hashed_password"]):
            return False
        self.collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )
        return user
    def update_profile(self, user_id: str, profile_data: ProfileUpdate) -> Optional[Dict[str, Any]]:
        """
        Actualizar el perfil del usuario
        """
        try:
            # Verificar si el usuario existe
            user = self.get_user_by_id(user_id)
            if not user:
                return None
            
            # Preparar datos de actualización
            update_data = {}
            
            # Si se está actualizando el email, verificar que no esté en uso
            if profile_data.email:
                # Verificar si el email ya existe para otro usuario
                existing_user = self.collection.find_one({
                    "email": profile_data.email.lower().strip(),
                    "_id": {"$ne": ObjectId(user_id)}
                })
                if existing_user:
                    return {"error": "El email ya está en uso por otro usuario"}
                update_data["email"] = profile_data.email.lower().strip()
            
            # Agregar solo los campos que se enviaron
            for field, value in profile_data.model_dump(exclude_unset=True).items():
                if value is not None and field != 'email':  # Email ya procesado
                    update_data[field] = value
            
            # Siempre actualizar el timestamp
            update_data["updated_at"] = datetime.now(timezone.utc)
            
            if update_data:
                # Actualizar el usuario
                result = self.collection.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": update_data}
                )
                
                if result.modified_count == 0:
                    return {"error": "No se pudo actualizar el perfil"}
            
            # Obtener el usuario actualizado
            updated_user = self.get_user_by_id(user_id)
            if updated_user:
                # Remover campos sensibles
                updated_user.pop("hashed_password", None)
                updated_user["_id"] = str(updated_user["_id"])
                
            return updated_user
            
        except Exception as e:
            return {"error": f"Error al actualizar perfil: {str(e)}"}
    
    def change_password(self, user_id: str, password_data: PasswordChange) -> Dict[str, Any]:
        """
        Cambiar la contraseña del usuario
        """
        try:
            # Verificar si el usuario existe
            user = self.get_user_by_id(user_id)
            if not user:
                return {"error": "Usuario no encontrado"}
            
            # Verificar la contraseña actual
            if not self.verify_password(password_data.current_password, user["hashed_password"]):
                return {"error": "Contraseña actual incorrecta"}
            
            # Validar que las nuevas contraseñas coincidan
            try:
                password_data.validate_passwords()
            except ValueError as e:
                return {"error": str(e)}
            
            # Actualizar la contraseña y el timestamp
            new_hashed_password = self.hash_password(password_data.new_password)
            
            result = self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            if result.modified_count == 0:
                return {"error": "No se pudo cambiar la contraseña"}
            
            return {"success": True, "message": "Contraseña actualizada exitosamente"}
            
        except Exception as e:
            return {"error": f"Error al cambiar contraseña: {str(e)}"}
    
    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtener el perfil completo del usuario
        """
        try:
            user = self.get_user_by_id(user_id)
            if user:
                # Remover campos sensibles
                user.pop("hashed_password", None)
                user["_id"] = str(user["_id"])
                return user
            return None
        except Exception as e:
            return None