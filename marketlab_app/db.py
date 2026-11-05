"""pyodbc connection lifecycle, parameterized execution and SQL error mapping (no secrets in messages)."""
from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import re
from typing import Any, Iterator

import pyodbc

from .config import Settings

pyodbc.pooling = True

SQL_ERROR_RE = re.compile(r"\((\d{3,6})\)\s*\(SQL")
MSG_RE = re.compile(r"\[SQL Server\](.*?)\s*\(\d{3,6}\)\s*\(SQL", re.S)


class DatabaseUnavailable(RuntimeError):
    """Cannot connect / login / driver missing. Message is safe to show."""


class SqlError(RuntimeError):
    def __init__(self, number: int | None, message: str, sqlstate: str = ""):
        super().__init__(f"SQL {number}: {message}")
        self.number = number
        self.message = message
        self.sqlstate = sqlstate


def connection_string(settings: Settings, database: str | None = None) -> str:
    parts = [
        f"Driver={{{settings.sql_driver}}}",
        f"Server={settings.sql_server}",
        f"Database={database or settings.sql_database}",
        f"Encrypt={settings.sql_encrypt}",
        f"TrustServerCertificate={settings.sql_trust_server_certificate}",
        "APP=MarketLabVN30",
    ]
    if settings.sql_auth == "sql":
        # Braces escape special characters; value never logged.
        pwd = settings.sql_password.replace("}", "}}")
        parts += [f"UID={settings.sql_user}", f"PWD={{{pwd}}}"]
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts) + ";"


def _redact(text: str, settings: Settings) -> str:
    if settings.sql_password:
        text = text.replace(settings.sql_password, "***")
    return re.sub(r"(?i)(PWD|Password)=[^;]*", r"\1=***", text)


def translate(exc: pyodbc.Error, settings: Settings) -> Exception:
    sqlstate = exc.args[0] if exc.args else ""
    raw = " ".join(str(a) for a in exc.args[1:]) if len(exc.args) > 1 else str(exc)
    raw = _redact(raw, settings)
    if sqlstate in ("08001", "08S01", "HYT00", "28000", "IM002", "IM003", "01000") and not SQL_ERROR_RE.search(raw):
        hint = {
            "IM002": "ODBC driver not found (install 'ODBC Driver 18 for SQL Server' or set MARKETLAB_SQL_DRIVER)",
            "28000": "login failed for the configured SQL account / Windows identity",
            "HYT00": "timeout while connecting or executing",
        }.get(sqlstate, "SQL Server not reachable (check MARKETLAB_SQL_SERVER and that the service runs)")
        return DatabaseUnavailable(f"{hint} [sqlstate {sqlstate}]")
    number = None
    m = SQL_ERROR_RE.search(raw)
    if m:
        number = int(m.group(1))
    mm = MSG_RE.search(raw)
    message = (mm.group(1) if mm else raw).strip()
    return SqlError(number, message[:500], sqlstate)


@contextlib.contextmanager
def connect(settings: Settings, database: str | None = None, autocommit: bool = True) -> Iterator[pyodbc.Connection]:
    try:
        cnxn = pyodbc.connect(connection_string(settings, database), timeout=settings.sql_login_timeout, autocommit=autocommit)
    except pyodbc.Error as exc:
        # Any failure while connecting (driver, network, login, unknown database) = unavailable, never a 500.
        t = translate(exc, settings)
        if isinstance(t, DatabaseUnavailable):
            raise t from None
        detail = {18456: "login failed", 4060: f"cannot open database '{database or settings.sql_database}'",
                  10061: "connection refused", 53: "server not found"}.get(t.number or 0, t.message[:200])
        raise DatabaseUnavailable(f"SQL Server unavailable: {detail} [sqlstate {t.sqlstate}, native {t.number}]") from None
    try:
        cnxn.timeout = settings.sql_query_timeout
        yield cnxn
    finally:
        with contextlib.suppress(Exception):
            cnxn.close()


def jsonable(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime,)):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, bool):
        return value
    return value


def rows(cursor: pyodbc.Cursor) -> list[dict]:
    if cursor.description is None:
        return []
    cols = [c[0] for c in cursor.description]
    return [{c: jsonable(v) for c, v in zip(cols, r)} for r in cursor.fetchall()]


def query(cnxn: pyodbc.Connection, sql: str, params: tuple | list = (), settings: Settings | None = None) -> list[dict]:
    try:
        cur = cnxn.cursor()
        cur.execute(sql, *params) if params else cur.execute(sql)
        return rows(cur)
    except pyodbc.Error as exc:
        raise translate(exc, settings or Settings()) from None


def query_sets(cnxn: pyodbc.Connection, sql: str, params: tuple | list = (), settings: Settings | None = None) -> list[list[dict]]:
    """All result sets of a batch / procedure call."""
    try:
        cur = cnxn.cursor()
        cur.execute(sql, *params) if params else cur.execute(sql)
        out = []
        while True:
            if cur.description is not None:
                out.append(rows(cur))
            if not cur.nextset():
                break
        return out
    except pyodbc.Error as exc:
        raise translate(exc, settings or Settings()) from None
