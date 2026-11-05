"""Settings from environment variables and an optional .env file (never committed)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ("DEMO_OFFLINE", "REAL_PRIVATE")
DB_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,99}$")


class ConfigError(ValueError):
    """Invalid configuration. Messages never contain secret values."""


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (no interpolation). Existing environment variables win."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    mode: str = "DEMO_OFFLINE"
    sql_server: str = "."
    sql_database: str = "MarketLabVN30_Demo"
    sql_driver: str = "ODBC Driver 18 for SQL Server"
    sql_auth: str = "windows"
    sql_user: str = ""
    sql_password: str = field(default="", repr=False)
    sql_encrypt: str = "yes"
    sql_trust_server_certificate: str = "yes"
    sql_login_timeout: int = 5
    sql_query_timeout: int = 60
    ops_database: str = "MarketLabVN30_Ops"
    host: str = "127.0.0.1"
    port: int = 8000
    ops_token: str = field(default="", repr=False)
    provider_python: str = ""
    provider_timeout_seconds: int = 180
    provider_min_interval_seconds: float = 0.4
    provider_max_attempts: int = 3
    eod_cutoff: str = "16:10"
    max_backfill_sessions: int = 40
    log_dir: Path = ROOT / "var" / "logs"

    @property
    def is_demo(self) -> bool:
        return self.mode == "DEMO_OFFLINE"

    def redacted(self) -> dict:
        return {
            "mode": self.mode,
            "sql_server": self.sql_server,
            "sql_database": self.sql_database,
            "sql_driver": self.sql_driver,
            "sql_auth": self.sql_auth,
            "sql_user": self.sql_user if self.sql_auth == "sql" else "",
            "sql_password": "***" if self.sql_password else "",
            "ops_database": self.ops_database,
            "host": self.host,
            "port": self.port,
            "ops_token": "configured" if self.ops_token else "not configured",
            "provider_python": "configured" if self.provider_python else "not configured",
            "eod_cutoff": self.eod_cutoff,
        }


def _int(env: dict, key: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(key, "")
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{key} must be in [{lo}, {hi}]")
    return value


def load_settings(env: dict[str, str] | None = None, dotenv: Path | None = None) -> Settings:
    merged: dict[str, str] = {}
    if env is None:
        merged.update(load_dotenv(dotenv or ROOT / ".env"))
        merged.update({k: v for k, v in os.environ.items() if k.startswith("MARKETLAB_")})
    else:
        merged.update(env)
    g = lambda k, d="": merged.get(k, d).strip()  # noqa: E731

    mode = g("MARKETLAB_MODE", "DEMO_OFFLINE").upper()
    if mode not in MODES:
        raise ConfigError(f"MARKETLAB_MODE must be one of {MODES}")
    database = g("MARKETLAB_SQL_DATABASE", "MarketLabVN30_Demo" if mode == "DEMO_OFFLINE" else "")
    if not database:
        raise ConfigError("MARKETLAB_SQL_DATABASE is required for REAL_PRIVATE (no automatic choice)")
    ops_db = g("MARKETLAB_OPS_DATABASE", "MarketLabVN30_Ops")
    for key, name in (("MARKETLAB_SQL_DATABASE", database), ("MARKETLAB_OPS_DATABASE", ops_db)):
        if not DB_NAME_RE.match(name):
            raise ConfigError(f"{key} has an unsafe database name")
    auth = g("MARKETLAB_SQL_AUTH", "windows").lower()
    if auth not in ("windows", "sql"):
        raise ConfigError("MARKETLAB_SQL_AUTH must be 'windows' or 'sql'")
    user, password = g("MARKETLAB_SQL_USER"), merged.get("MARKETLAB_SQL_PASSWORD", "")
    if auth == "sql" and (not user or not password):
        raise ConfigError("SQL authentication needs MARKETLAB_SQL_USER and MARKETLAB_SQL_PASSWORD")
    host = g("MARKETLAB_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ConfigError("MARKETLAB_HOST must be a loopback address; LAN exposure is not supported")
    token = merged.get("MARKETLAB_OPS_TOKEN", "").strip()
    if token and len(token) < 32:
        raise ConfigError("MARKETLAB_OPS_TOKEN must be at least 32 characters (use scripts/Setup-MarketLab.ps1)")
    cutoff = g("MARKETLAB_EOD_CUTOFF", "16:10")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", cutoff):
        raise ConfigError("MARKETLAB_EOD_CUTOFF must be HH:MM")
    yes_no = lambda k, d: g(k, d).lower() if g(k, d).lower() in ("yes", "no", "strict", "optional", "mandatory") else d  # noqa: E731
    log_dir = g("MARKETLAB_LOG_DIR")
    return Settings(
        mode=mode,
        sql_server=g("MARKETLAB_SQL_SERVER", "."),
        sql_database=database,
        sql_driver=g("MARKETLAB_SQL_DRIVER", "ODBC Driver 18 for SQL Server"),
        sql_auth=auth,
        sql_user=user,
        sql_password=password,
        sql_encrypt=yes_no("MARKETLAB_SQL_ENCRYPT", "yes"),
        sql_trust_server_certificate=yes_no("MARKETLAB_SQL_TRUST_SERVER_CERTIFICATE", "yes"),
        sql_login_timeout=_int(merged, "MARKETLAB_SQL_LOGIN_TIMEOUT", 5, 1, 60),
        sql_query_timeout=_int(merged, "MARKETLAB_SQL_QUERY_TIMEOUT", 60, 1, 600),
        ops_database=ops_db,
        host=host,
        port=_int(merged, "MARKETLAB_PORT", 8000, 1024, 65535),
        ops_token=token,
        provider_python=g("MARKETLAB_PROVIDER_PYTHON"),
        provider_timeout_seconds=_int(merged, "MARKETLAB_PROVIDER_TIMEOUT_SECONDS", 180, 10, 1800),
        provider_max_attempts=_int(merged, "MARKETLAB_PROVIDER_MAX_ATTEMPTS", 3, 1, 6),
        eod_cutoff=cutoff,
        max_backfill_sessions=_int(merged, "MARKETLAB_MAX_BACKFILL_SESSIONS", 40, 1, 400),
        log_dir=Path(log_dir) if log_dir else ROOT / "var" / "logs",
    )
