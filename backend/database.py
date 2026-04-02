from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _default_sqlite_path() -> str:
    db_path = Path(__file__).resolve().parent / "club_payment.sqlite3"
    return f"sqlite:///{db_path}"


def _database_url() -> str:
    return os.getenv("DATABASE_URL", _default_sqlite_path())


def _create_engine():
    database_url = _database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


Base = declarative_base()
engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    api_token = Column(String(255), nullable=False, unique=True)
    username = Column(String(255), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=True)


class DeviceAssignmentRecord(Base):
    __tablename__ = "device_assignments"

    device_id = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
