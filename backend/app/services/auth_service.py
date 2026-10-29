from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


class AuthService:
    def register(self, db: Session, payload: RegisterRequest) -> User:
        existing_user = db.scalar(select(User).where(User.email == payload.email))
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists.",
            )

        user = User(
            name=payload.name,
            email=payload.email,
            password_hash=get_password_hash(payload.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def authenticate(self, db: Session, payload: LoginRequest) -> User:
        identifier = payload.username.strip()
        user = db.scalar(
            select(User).where(
                or_(
                    User.email == identifier,
                    User.name == identifier,
                )
            )
        )
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )
        return user

    def get_user_by_email(self, db: Session, email: str) -> User | None:
        return db.scalar(select(User).where(User.email == email))

    def build_token_response(self, user: User, settings: Settings) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user.email, settings=settings),
            user=UserResponse.model_validate(user),
        )
