from __future__ import annotations

from typing import Optional

from flask import Request

from errors import APIError
from users import ADMIN_ROLES, User, get_user_store


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
        raise APIError("Ungueltiges oder inaktives Token", 401)
    if require_admin and user.role not in ADMIN_ROLES:
        raise APIError("Nur Administratoren duerfen diese Aktion ausfuehren", 403)
    return user
