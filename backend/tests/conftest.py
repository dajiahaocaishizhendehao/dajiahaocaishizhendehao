"""测试夹具。

默认使用内存 SQLite 运行，保证没有 PostgreSQL 时也能执行单元测试；
生产与联调仍使用 PostgreSQL（见 docs/DECISIONS.md D-009）。
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import security  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    user = User(
        username="admin",
        display_name="管理员",
        password_hash=security.hash_password("Passw0rd!"),
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def viewer_user(db_session: Session) -> User:
    user = User(
        username="viewer",
        display_name="只读用户",
        password_hash=security.hash_password("Passw0rd!"),
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(client: TestClient, username: str, password: str = "Passw0rd!") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    return login(client, admin_user.username)


@pytest.fixture()
def viewer_headers(client: TestClient, viewer_user: User) -> dict[str, str]:
    return login(client, viewer_user.username)
