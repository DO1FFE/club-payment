import os
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Optional


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


class UserStore:
    def __init__(self) -> None:
        self._users: Dict[int, User] = {}
        self._next_id = 1

    def list_users(self) -> Iterable[User]:
        return list(self._users.values())

    def create_user(self, name: str, role: Role, active: bool, api_token: Optional[str] = None) -> User:
        token = api_token or secrets.token_urlsafe(32)
        user = User(id=self._next_id, name=name, role=role, active=active, api_token=token)
        self._users[self._next_id] = user
        self._next_id += 1
        return user

    def get_by_token(self, token: str) -> Optional[User]:
        for user in self._users.values():
            if user.api_token == token:
                return user
        return None

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self._users.get(user_id)

    def update_user(
        self,
        user_id: int,
        name: Optional[str] = None,
        role: Optional[Role] = None,
        active: Optional[bool] = None,
    ) -> Optional[User]:
        user = self._users.get(user_id)
        if not user:
            return None
        if name is not None:
            user.name = name
        if role is not None:
            user.role = role
        if active is not None:
            user.active = active
        return user


_STORE: Optional[UserStore] = None


def get_user_store() -> UserStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        _STORE = UserStore()
        admin_token = os.getenv("ADMIN_API_TOKEN")
        if admin_token:
            admin_name = os.getenv("ADMIN_NAME", "Admin")
            _STORE.create_user(name=admin_name, role=Role.ADMIN, active=True, api_token=admin_token)
    return _STORE
