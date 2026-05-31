import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models as _models
from app.models import User
from app.services.security import create_access_token, hash_password

TEST_PASSWORD = "test-password"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all(
        [
            User(
                email="admin@example.com",
                hashed_password=TEST_PASSWORD_HASH,
                role="admin",
            ),
            User(
                email="operator@example.com",
                hashed_password=TEST_PASSWORD_HASH,
                role="operator",
            ),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    original_session_factory = app.state.session_factory
    app.state.session_factory = lambda: db_session
    with TestClient(app) as test_client:
        test_client.headers.update(
            {"Authorization": f"Bearer {create_access_token('admin@example.com')}"}
        )
        yield test_client
    app.state.session_factory = original_session_factory
    app.dependency_overrides.clear()
