from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.config import settings
from app.db.session import get_db
from app.models.settings import UserSettings
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    email = decode_access_token(token)
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if email is None:
        raise credentials_error
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_error
    return user


def get_or_create_settings(db: Session, user: User) -> UserSettings:
    row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if row is None:
        row = UserSettings(user_id=user.id, demo_mode=settings.DEMO_MODE)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def resolve_demo_mode(demo: bool | None, db: Session, user: User) -> bool:
    """
    An explicit `?demo=` query param always wins; otherwise use the user's
    saved toggle, initialized from the server default for new settings rows.
    Never mixes simulated and real data — see app.services.demo_data.
    """
    if demo is not None:
        return demo
    return get_or_create_settings(db, user).demo_mode
