"""Workspace identity comes from verified claims; loopback demo mode is explicit."""

from dataclasses import dataclass
from ipaddress import ip_address, ip_network

import jwt
from fastapi import HTTPException, Request

from .config import Settings


@dataclass(frozen=True)
class Identity:
    tenant: str
    user: str
    role: str = "viewer"

    def require_editor(self):
        if self.role not in {"editor", "admin"}:
            raise HTTPException(403, "Your workspace role cannot change knowledge sources")

    def require_admin(self):
        if self.role != "admin":
            raise HTTPException(403, "Workspace administrator role required")


class Authentication:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.local_networks = [
            ip_network(value.strip()) for value in settings.local_client_networks.split(",")
        ]
        self.jwks = (
            jwt.PyJWKClient(settings.oidc_jwks_url, timeout=5, cache_keys=True)
            if settings.auth_mode == "oidc"
            else None
        )

    def __call__(self, request: Request) -> Identity:
        if self.settings.auth_mode == "local":
            # Host validation also rejects DNS rebinding and public reverse-proxy hosts.
            host = request.client.host if request.client else ""
            try:
                allowed = any(ip_address(host) in network for network in self.local_networks)
            except ValueError:
                allowed = host == "testclient"
            if not allowed:
                raise HTTPException(403, "Local workspace is available on this computer only")
            return Identity(self.settings.local_tenant, "local-owner", "admin")
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(401, "Connect a workspace access token")
        token = header[7:]
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub", "workspace_id"]},
            )
            tenant, user = claims["workspace_id"], claims["sub"]
            if not isinstance(tenant, str) or not tenant or not isinstance(user, str) or not user:
                raise ValueError("Invalid workspace identity")
            roles = claims.get("roles", [])
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise ValueError("Roles must be a list of role names")
            role = next((r for r in ("admin", "editor", "viewer") if r in roles), "viewer")
            return Identity(tenant, user, role)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as error:
            raise HTTPException(401, "Workspace token is invalid or expired") from error
