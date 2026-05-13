from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from enum import Enum
from getpass import getpass
from typing import Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from database import UserRecord, init_database
from database import SessionLocal
from organizations import get_organization_store


class Role(str, Enum):
    SYSTEM_ADMIN = "system_admin"
    OV_ADMIN = "ov_admin"
    ADMIN = "ov_admin"
    KASSIERER = "kassierer"

    @classmethod
    def from_value(cls, value: str | "Role") -> "Role":
        if isinstance(value, Role):
            return value
        if value == "admin":
            return cls.OV_ADMIN
        return cls(value)


ADMIN_ROLES = {Role.SYSTEM_ADMIN, Role.OV_ADMIN}


@dataclass
class User:
    id: int
    name: str
    role: Role
    active: bool
    api_token: str
    username: Optional[str] = None
    password_hash: Optional[str] = None
    organization_id: Optional[int] = None


class UserStore:
    @staticmethod
    def _to_user(record: UserRecord) -> User:
        return User(
            id=record.id,
            name=record.name,
            role=Role.from_value(record.role),
            active=record.active,
            api_token=record.api_token,
            username=record.username,
            password_hash=record.password_hash,
            organization_id=record.organization_id,
        )

    def list_users(self, organization_id: int | None = None, include_system_admins: bool = False) -> Iterable[User]:
        with SessionLocal() as session:
            query = session.query(UserRecord)
            if organization_id is not None:
                query = query.filter(UserRecord.organization_id == organization_id)
                if include_system_admins:
                    query = query.union(
                        session.query(UserRecord).filter(UserRecord.role == Role.SYSTEM_ADMIN.value)
                    )
            records = query.order_by(UserRecord.id.asc()).all()
            return [self._to_user(record) for record in records]

    def create_user(
        self,
        name: str,
        role: Role,
        active: bool,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password_hash: Optional[str] = None,
        organization_id: Optional[int] = None,
    ) -> User:
        normalized_role = Role.from_value(role)
        if normalized_role == Role.SYSTEM_ADMIN:
            organization_id = None
        elif organization_id is None:
            organization_id = get_organization_store().ensure_default_organization().id

        token = api_token or secrets.token_urlsafe(32)
        with SessionLocal() as session:
            record = UserRecord(
                name=name,
                role=normalized_role.value,
                active=active,
                api_token=token,
                username=username,
                password_hash=password_hash,
                organization_id=organization_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_user(record)

    def get_by_token(self, token: str) -> Optional[User]:
        with SessionLocal() as session:
            record = session.query(UserRecord).filter(UserRecord.api_token == token).first()
            return self._to_user(record) if record else None

    def get_by_id(self, user_id: int) -> Optional[User]:
        with SessionLocal() as session:
            record = session.get(UserRecord, user_id)
            return self._to_user(record) if record else None

    def get_by_username(self, username: str) -> Optional[User]:
        with SessionLocal() as session:
            record = session.query(UserRecord).filter(UserRecord.username == username).first()
            return self._to_user(record) if record else None

    def has_admin_user(self) -> bool:
        with SessionLocal() as session:
            record = (
                session.query(UserRecord.id)
                .filter(UserRecord.role.in_([Role.SYSTEM_ADMIN.value, Role.OV_ADMIN.value, "admin"]))
                .first()
            )
            return record is not None

    def has_system_admin_user(self) -> bool:
        with SessionLocal() as session:
            record = session.query(UserRecord.id).filter(UserRecord.role == Role.SYSTEM_ADMIN.value).first()
            return record is not None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.get_by_username(username)
        if not user or not user.password_hash:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        return user

    @staticmethod
    def hash_password(password: str) -> str:
        return generate_password_hash(password)

    def update_user(
        self,
        user_id: int,
        name: Optional[str] = None,
        role: Optional[Role] = None,
        active: Optional[bool] = None,
        username: Optional[str] = None,
        password_hash: Optional[str] = None,
        organization_id: Optional[int] = None,
        clear_organization: bool = False,
    ) -> Optional[User]:
        with SessionLocal() as session:
            record = session.get(UserRecord, user_id)
            if not record:
                return None
            if name is not None:
                record.name = name
            if username is not None:
                record.username = username
            if role is not None:
                normalized_role = Role.from_value(role)
                record.role = normalized_role.value
                if normalized_role == Role.SYSTEM_ADMIN:
                    record.organization_id = None
            if active is not None:
                record.active = active
            if password_hash is not None:
                record.password_hash = password_hash
            if clear_organization:
                record.organization_id = None
            elif organization_id is not None:
                record.organization_id = organization_id
            session.commit()
            session.refresh(record)
            return self._to_user(record)

    def delete_user(self, user_id: int) -> bool:
        with SessionLocal() as session:
            record = session.get(UserRecord, user_id)
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True


_STORE: Optional[UserStore] = None


def _bootstrap_admin(store: UserStore) -> None:
    admin_token = os.getenv("ADMIN_API_TOKEN")
    if not admin_token:
        return

    if store.get_by_token(admin_token):
        return

    admin_name = os.getenv("ADMIN_NAME", "System Admin")
    admin_username = os.getenv("ADMIN_USERNAME", admin_name)
    admin_password = os.getenv("ADMIN_PASSWORD")
    admin_role = Role.from_value(os.getenv("ADMIN_ROLE", Role.SYSTEM_ADMIN.value))
    organization_id = None
    if admin_role != Role.SYSTEM_ADMIN:
        organization_id = get_organization_store().ensure_default_organization().id
    password_hash = store.hash_password(admin_password) if admin_password else None
    store.create_user(
        name=admin_name,
        role=admin_role,
        active=True,
        api_token=admin_token,
        username=admin_username,
        password_hash=password_hash,
        organization_id=organization_id,
    )


def _prompt_non_empty_input(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Eingabe darf nicht leer sein.")


def _prompt_password(min_length: int = 8) -> str:
    while True:
        password = getpass("Passwort fuer System-Admin eingeben: ").strip()
        if len(password) < min_length:
            print(f"Passwort muss mindestens {min_length} Zeichen lang sein.")
            continue
        password_confirm = getpass("Passwort bestaetigen: ").strip()
        if password != password_confirm:
            print("Passwoerter stimmen nicht ueberein.")
            continue
        return password


def _bootstrap_admin_interactive(store: UserStore) -> None:
    print("Kein Admin-Benutzer gefunden. Initiale System-Admin-Anlage wird gestartet.")

    while True:
        username = _prompt_non_empty_input("System-Admin-Benutzername: ")
        if store.get_by_username(username):
            print("Benutzername ist bereits vergeben.")
            continue
        break

    password = _prompt_password()
    display_name = input("Anzeigename (optional, Enter fuer Benutzername): ").strip() or username

    store.create_user(
        name=display_name,
        role=Role.SYSTEM_ADMIN,
        active=True,
        username=username,
        password_hash=store.hash_password(password),
    )
    print(f"System-Admin-Benutzer '{username}' wurde erfolgreich erstellt.")


def get_user_store() -> UserStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        init_database()
        _STORE = UserStore()
        _bootstrap_admin(_STORE)
        if not _STORE.has_admin_user():
            _bootstrap_admin_interactive(_STORE)
    return _STORE
