from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker


DEFAULT_ORGANIZATION_NAME = "DARC e.V. OV Essen-Mitte"
DEFAULT_ORGANIZATION_DOK = "L11"
DEFAULT_ORGANIZATION_SLUG = "l11"
DEFAULT_PLATFORM_FEE_BASIS_POINTS = 100


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


class OrganizationRecord(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    dok = Column(String(32), nullable=False)
    slug = Column(String(64), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    stripe_connect_account_id = Column(String(255), nullable=True)
    stripe_connect_onboarding_complete = Column(Boolean, nullable=False, default=False)
    stripe_location_id = Column(String(255), nullable=True)
    platform_fee_percent = Column(Integer, nullable=True)
    platform_fee_basis_points = Column(Integer, nullable=False, default=DEFAULT_PLATFORM_FEE_BASIS_POINTS)
    address_line1 = Column(String(255), nullable=True)
    address_postal_code = Column(String(32), nullable=True)
    address_city = Column(String(128), nullable=True)
    address_country = Column(String(2), nullable=False, default="DE")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    api_token = Column(String(255), nullable=False, unique=True)
    username = Column(String(255), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)


class DeviceAssignmentRecord(Base):
    __tablename__ = "device_assignments"
    __table_args__ = (UniqueConstraint("organization_id", "device_id", name="uq_device_assignment_organization_device"),)

    # Die bestehende SQLite-Tabelle nutzt device_id bereits als Primaerschluessel.
    # Wir erhalten das fuer eine verlustfreie Migration und erzwingen den OV-Kontext zusaetzlich.
    device_id = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)


class PendingDeviceRecord(Base):
    __tablename__ = "pending_devices"

    device_id = Column(String(255), primary_key=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(255), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    last_seen_at = Column(DateTime, nullable=False)


class ProductRecord(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    price_cents = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)


class PaymentLogRecord(Base):
    __tablename__ = "payment_logs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    stripe_payment_intent_id = Column(String(255), nullable=False, unique=True)
    stripe_charge_id = Column(String(255), nullable=True)
    amount_cents = Column(Integer, nullable=False)
    application_fee_amount_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(16), nullable=False, default="eur")
    item = Column(Text, nullable=False)
    cashier_user_id = Column(Integer, nullable=True)
    cashier_name = Column(String(255), nullable=True)
    device_id = Column(String(255), nullable=True)
    status = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _table_columns(connection, table_name: str) -> set[str]:
    inspector = inspect(connection)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(connection, table_name: str, column_name: str, definition: str) -> None:
    if column_name in _table_columns(connection, table_name):
        return
    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {definition}"))


def _ensure_default_organization(connection) -> int:
    now = _utcnow()
    existing = connection.execute(
        text("SELECT id FROM organizations WHERE slug = :slug"),
        {"slug": DEFAULT_ORGANIZATION_SLUG},
    ).first()
    if existing:
        return int(existing[0])

    connection.execute(
        text(
            """
            INSERT INTO organizations (
                name, dok, slug, active, stripe_connect_onboarding_complete,
                platform_fee_basis_points, address_country, created_at, updated_at
            )
            VALUES (
                :name, :dok, :slug, 1, 0,
                :fee_basis_points, 'DE', :created_at, :updated_at
            )
            """
        ),
        {
            "name": DEFAULT_ORGANIZATION_NAME,
            "dok": DEFAULT_ORGANIZATION_DOK,
            "slug": DEFAULT_ORGANIZATION_SLUG,
            "fee_basis_points": int(os.getenv("PLATFORM_FEE_BASIS_POINTS", DEFAULT_PLATFORM_FEE_BASIS_POINTS)),
            "created_at": now,
            "updated_at": now,
        },
    )
    created = connection.execute(
        text("SELECT id FROM organizations WHERE slug = :slug"),
        {"slug": DEFAULT_ORGANIZATION_SLUG},
    ).first()
    if not created:
        raise RuntimeError("Default-Organisation konnte nicht angelegt werden.")
    return int(created[0])


def _migrate_roles_and_assignments(connection, default_organization_id: int) -> None:
    user_columns = _table_columns(connection, "users")
    if "organization_id" in user_columns:
        first_admin = connection.execute(
            text("SELECT id FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1")
        ).first()
        initial_admin_as_system_admin = os.getenv("INITIAL_ADMIN_AS_SYSTEM_ADMIN", "true").lower() in {
            "1",
            "true",
            "yes",
            "ja",
            "on",
        }
        if first_admin and initial_admin_as_system_admin:
            connection.execute(
                text("UPDATE users SET role = 'system_admin', organization_id = NULL WHERE id = :id"),
                {"id": int(first_admin[0])},
            )

        connection.execute(
            text(
                """
                UPDATE users
                   SET role = 'ov_admin',
                       organization_id = COALESCE(organization_id, :organization_id)
                 WHERE role = 'admin'
                """
            ),
            {"organization_id": default_organization_id},
        )
        connection.execute(
            text(
                """
                UPDATE users
                   SET organization_id = :organization_id
                 WHERE role IN ('ov_admin', 'kassierer') AND organization_id IS NULL
                """
            ),
            {"organization_id": default_organization_id},
        )

    for table_name in ("products", "device_assignments"):
        columns = _table_columns(connection, table_name)
        if "organization_id" in columns:
            connection.execute(
                text(f"UPDATE {table_name} SET organization_id = :organization_id WHERE organization_id IS NULL"),
                {"organization_id": default_organization_id},
            )

    pending_columns = _table_columns(connection, "pending_devices")
    if "organization_id" in pending_columns:
        connection.execute(
            text("UPDATE pending_devices SET organization_id = :organization_id WHERE organization_id IS NULL"),
            {"organization_id": default_organization_id},
        )


def _run_idempotent_migrations() -> None:
    with engine.begin() as connection:
        _add_column_if_missing(connection, "users", "organization_id", "organization_id INTEGER NULL")
        _add_column_if_missing(connection, "products", "organization_id", "organization_id INTEGER NULL")
        _add_column_if_missing(connection, "device_assignments", "organization_id", "organization_id INTEGER NULL")
        _add_column_if_missing(connection, "pending_devices", "organization_id", "organization_id INTEGER NULL")

        default_organization_id = _ensure_default_organization(connection)
        _migrate_roles_and_assignments(connection, default_organization_id)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    _run_idempotent_migrations()
