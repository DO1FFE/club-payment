from __future__ import annotations

import os
import secrets
from getpass import getpass
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from database import SessionLocal, UserRecord, init_database


class Role(str, Enum):
    ADMIN = "admin"
    KASSIERER = "kassierer"


@dataclass
class User:
    id: int
    name: str
    role: Role
    active: bool
    api_token: str
    username: Optional[str] = None
    password_hash: Optional[str] = None


class UserStore:
    @staticmethod
    def _to_user(record: UserRecord) -> User:
        return User(
            id=record.id,
            name=record.name,
            role=Role(record.role),
            active=record.active,
            api_token=record.api_token,
            username=record.username,
            password_hash=record.password_hash,
        )

    def list_users(self) -> Iterable[User]:
        with SessionLocal() as session:
            records = session.query(UserRecord).order_by(UserRecord.id.asc()).all()
            return [self._to_user(record) for record in records]

    def create_user(
        self,
        name: str,
        role: Role,
        active: bool,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> User:
        token = api_token or secrets.token_urlsafe(32)
        with SessionLocal() as session:
            record = UserRecord(
                name=name,
                role=role.value,
                active=active,
                api_token=token,
                username=username,
                password_hash=password_hash,
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
            record = session.query(UserRecord.id).filter(UserRecord.role == Role.ADMIN.value).first()
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
                record.role = role.value
            if active is not None:
                record.active = active
            if password_hash is not None:
                record.password_hash = password_hash
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

    admin_name = os.getenv("ADMIN_NAME", "Admin")
    admin_username = os.getenv("ADMIN_USERNAME", admin_name)
    admin_password = os.getenv("ADMIN_PASSWORD")
    password_hash = store.hash_password(admin_password) if admin_password else None
    store.create_user(
        name=admin_name,
        role=Role.ADMIN,
        active=True,
        api_token=admin_token,
        username=admin_username,
        password_hash=password_hash,
    )


def _prompt_non_empty_input(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Eingabe darf nicht leer sein.")


def _prompt_password(min_length: int = 8) -> str:
    while True:
        password = getpass("Passwort für Admin eingeben: ").strip()
        if len(password) < min_length:
            print(f"Passwort muss mindestens {min_length} Zeichen lang sein.")
            continue
        password_confirm = getpass("Passwort bestätigen: ").strip()
        if password != password_confirm:
            print("Passwörter stimmen nicht überein.")
            continue
        return password


def _bootstrap_admin_interactive(store: UserStore) -> None:
    print("Kein Admin-Benutzer gefunden. Initiale Admin-Anlage wird gestartet.")

    while True:
        username = _prompt_non_empty_input("Admin-Benutzername: ")
        if store.get_by_username(username):
            print("Benutzername ist bereits vergeben.")
            continue
        break

    password = _prompt_password()
    display_name = input("Anzeigename (optional, Enter für Benutzername): ").strip() or username

    store.create_user(
        name=display_name,
        role=Role.ADMIN,
        active=True,
        username=username,
        password_hash=store.hash_password(password),
    )
    print(f"Admin-Benutzer '{username}' wurde erfolgreich erstellt.")


def get_user_store() -> UserStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        init_database()
        _STORE = UserStore()
        _bootstrap_admin(_STORE)
        if not _STORE.has_admin_user():
            _bootstrap_admin_interactive(_STORE)
    return _STORE
