"""Server-side identity configuration shared by all API routes."""

import json
import os
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass(frozen=True)
class Principal:
    tenant: str
    user: str
    role: str = "customer"


def make_auth(tokens=None):
    """Resolve identity from trusted configuration, never from request fields."""
    raw = tokens if tokens is not None else json.loads(os.environ.get("API_TOKENS", "{}"))
    if not raw or any(len(token) < 24 for token in raw):
        raise ValueError("Configure API_TOKENS with random tokens of at least 24 characters")
    identities = {token: Principal(**value) for token, value in raw.items()}
    if any(
        not p.tenant or not p.user or p.role not in {"customer", "operator"}
        for p in identities.values()
    ):
        raise ValueError("Invalid configured identity")
    bearer = HTTPBearer(auto_error=False)

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials:
            for token, principal in identities.items():
                if secrets.compare_digest(credentials.credentials.encode(), token.encode()):
                    return principal
        raise HTTPException(
            401, "Valid bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )

    return authenticate
