from __future__ import annotations

from typing import Optional

from flask import Request

from errors import APIError
from users import Role, User, get_user_store


def _extract_bearer_token(auth_header: Optional[str]) -> str:
    if not auth_header:
        raise APIError("Authorization-Header fehlt", 401)
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise APIError("Authorization-Header muss 'Bearer <token>' enthalten", 401)
    return parts[1].strip()


def authenticate_request(request: Request, require_admin: bool = False) -> User:
    token = _extract_bearer_token(request.headers.get("Authorization"))
    store = get_user_store()
    user = store.get_by_token(token)
    if not user or not user.active:
        raise APIError("Ungültiges oder inaktives Token", 401)
    if require_admin and user.role != Role.ADMIN:
        raise APIError("Nur Administratoren dürfen diese Aktion ausführen", 403)
    return user
