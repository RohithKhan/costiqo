from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import Settings, get_settings
from app.utils.time_utils import utc_now


ALGORITHM = "HS256"
password_hasher = PasswordHasher()


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Argon2Error:
        return False


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def create_access_token(
    subject: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    active_settings = settings or get_settings()
    expire_at = utc_now() + (
        expires_delta
        or timedelta(minutes=active_settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire_at}
    return jwt.encode(payload, active_settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            active_settings.secret_key,
            algorithms=[ALGORITHM],
        )
    except JWTError as exc:  # pragma: no cover - fast path exercised in API tests
        raise ValueError("Invalid authentication token") from exc
    subject = payload.get("sub")
    if not subject:
        raise ValueError("Token missing subject")
    return str(subject)
