from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.dependencies import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.register(db, payload)
    return auth_service.build_token_response(user, request.app.state.settings)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.authenticate(db, payload)
    return auth_service.build_token_response(user, request.app.state.settings)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
