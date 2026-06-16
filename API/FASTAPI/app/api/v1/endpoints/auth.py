from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.users_fake import FAKE_USERS
from app.core.security import verify_password, create_access_token
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = FAKE_USERS.get(form_data.username)

    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos",
        )

    token = create_access_token(subject=user["username"])
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(current_user=Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "full_name": current_user.get("full_name"),
        "role": current_user.get("role", "user"),
    }
