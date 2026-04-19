"""Bearer-token auth for the FastAPI surface.

Shared-secret pattern: the operator sets AUTH_TOKEN in the environment and
every non-/health request must carry `Authorization: Bearer <AUTH_TOKEN>`.
AUTH_TOKEN is required — create_app refuses to start without it, so the
service cannot accidentally run unauthenticated.

Not user auth — there are no user accounts. This is the smallest credible
gate before binding anywhere beyond 127.0.0.1.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Request, status


async def require_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected: str = request.app.state.auth_token  # set by create_app

    token: str | None = None
    if authorization is not None:
        scheme, _, tok = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = tok

    # EventSource (the SSE client) can't set custom headers, so the frontend
    # passes the token via ?token= on streaming URLs. Bearer header wins
    # when both are present.
    if token is None:
        token = request.query_params.get("token")

    if not token or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
