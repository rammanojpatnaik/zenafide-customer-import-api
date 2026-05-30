from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.services.security import hash_password


def seed_demo_users(db: Session) -> None:
    if not settings.seed_demo_users:
        return

    demo_users = [
        (settings.admin_email, settings.admin_password, "admin"),
        (settings.operator_email, settings.operator_password, "operator"),
    ]
    for email, password, role in demo_users:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is None:
            db.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=role,
                )
            )
    db.commit()
