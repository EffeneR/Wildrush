"""Service configuration, read from ``WR_*`` environment variables (pydantic-settings)."""

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_bind(value: str) -> tuple[str, int]:
    """Parse ``host:port`` (IPv6 as ``[::1]:8080``)."""
    value = value.strip()
    if value.startswith("["):
        host, sep, port_s = value[1:].partition("]:")
        if not sep:
            raise ValueError("bind must look like [ipv6]:port")
    else:
        host, sep, port_s = value.rpartition(":")
        if not sep:
            raise ValueError("bind must look like host:port")
    if not host:
        raise ValueError("bind host is empty")
    try:
        port = int(port_s)
    except ValueError as exc:
        raise ValueError("bind port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("bind port out of range")
    return host, port


class Settings(BaseSettings):
    """All settings come from the environment with the ``WR_`` prefix.

    Secrets (database password) should be provided through ``WR_DATABASE_URL`` in a
    protected environment file or, preferably, ``WR_DATABASE_PASSWORD_FILE``.
    """

    model_config = SettingsConfigDict(env_prefix="WR_", extra="ignore", case_sensitive=False)

    # --- infrastructure -------------------------------------------------------------
    database_url: str = Field(description="SQLAlchemy URL, e.g. postgresql+psycopg://user@host:5432/db")
    database_password_file: str | None = Field(
        default=None, description="Optional file whose content replaces the password in database_url"
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    bind: str = "127.0.0.1:8080"
    public_base_url: str = "http://127.0.0.1:8080"
    dev_allow_http: bool = False
    forwarded_allow_ips: str = "127.0.0.1,::1"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    api_docs: bool = False
    max_body_bytes: int = Field(default=65536, ge=1024, le=10 * 1024 * 1024)

    # --- lifetimes ----------------------------------------------------------------------
    ticket_ttl_s: int = Field(default=60, ge=10, le=600)
    session_ttl_h: float = Field(default=12.0, gt=0, le=24 * 30)
    invite_ttl_s: int = Field(default=300, ge=10, le=86400)

    # --- matchmaker -----------------------------------------------------------------------
    matchmaker_enabled: bool = True
    matchmaker_interval_s: float = Field(default=1.0, gt=0, le=60)
    mm_max_latency_ms: int = Field(default=150, ge=1, le=10000)
    mm_region_relax_s: float = Field(default=60.0, ge=0)
    mm_casual_bot_wait_s: float = Field(default=20.0, ge=0)

    # --- servers / allocation -----------------------------------------------------------
    server_stale_s: float = Field(default=30.0, gt=0, description="server browser / allocation freshness")
    allocation_timeout_s: float = Field(default=45.0, gt=0, description="allocating -> cancelled after this")
    private_alloc_wait_s: float = Field(default=20.0, ge=0, le=120)
    host_lost_s: float = Field(default=120.0, gt=0, description="ready/running match cancelled if host silent")
    match_max_age_s: float = Field(default=3600.0, gt=0)
    private_max_players: int = Field(default=10, ge=1, le=10)
    private_max_observers: int = Field(default=10, ge=0, le=50)

    # --- rate limiting --------------------------------------------------------------------
    rate_limit_enabled: bool = True
    server_rate_limit_per_min: int = Field(default=1200, ge=1)

    # --- meta ----------------------------------------------------------------------------
    protocol_version: int = Field(default=1, ge=0)
    service_build: str = Field(default="dev", max_length=64)

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        v = v.strip()
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        if not v.startswith("postgresql+psycopg://"):
            raise ValueError("WR_DATABASE_URL must be a postgresql:// or postgresql+psycopg:// URL")
        return v

    @field_validator("bind")
    @classmethod
    def _check_bind(cls, v: str) -> str:
        parse_bind(v)
        return v.strip()

    @model_validator(mode="after")
    def _check_public_url(self) -> Settings:
        parts = urlsplit(self.public_base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("WR_PUBLIC_BASE_URL must be an absolute http(s) URL")
        if parts.scheme == "http" and not is_loopback_host(parts.hostname) and not self.dev_allow_http:
            raise ValueError(
                "WR_PUBLIC_BASE_URL must use https for non-loopback hosts "
                "(set WR_DEV_ALLOW_HTTP=true only for isolated development networks)"
            )
        return self

    @property
    def bind_host(self) -> str:
        return parse_bind(self.bind)[0]

    @property
    def bind_port(self) -> int:
        return parse_bind(self.bind)[1]
