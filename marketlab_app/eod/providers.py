"""EOD providers. The real one runs vnstock (KBS) in an isolated subprocess; the fake one is for tests ONLY."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..config import ROOT, Settings

BRIDGE = Path(__file__).with_name("kbs_bridge.py")


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class FetchResult:
    rows: dict[str, list[dict]]           # symbol -> raw candle dicts
    errors: dict[str, str]                # symbol -> error text (after retries)
    meta: dict = field(default_factory=dict)


class Provider(Protocol):
    source_code: str
    is_real: bool

    def fetch(self, symbols: list[str], start: dt.date, end: dt.date) -> FetchResult: ...


class VnstockKbsProvider:
    """Calls MARKETLAB_PROVIDER_PYTHON -I kbs_bridge.py; kill on timeout; no shell, no secrets."""
    source_code = "KBS_VNSTOCK"
    is_real = True

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.provider_python:
            raise ProviderError("PROVIDER_NOT_CONFIGURED",
                                "MARKETLAB_PROVIDER_PYTHON is not set (interpreter with vnstock installed); see docs/EOD_DATA_CONTRACT.md")
        self.python = Path(settings.provider_python)
        if not self.python.is_file():
            raise ProviderError("PROVIDER_NOT_CONFIGURED", "MARKETLAB_PROVIDER_PYTHON does not point to an existing python.exe")
        self._cache: dict[tuple, FetchResult] = {}

    def fetch(self, symbols: list[str], start: dt.date, end: dt.date) -> FetchResult:
        key = (tuple(symbols), start, end)
        if key in self._cache:
            return self._cache[key]
        work = ROOT / "var" / "provider_tmp"
        work.mkdir(parents=True, exist_ok=True)
        tag = uuid.uuid4().hex
        req, resp = work / f"req_{tag}.json", work / f"resp_{tag}.json"
        req.write_text(json.dumps({"symbols": symbols, "start": start.isoformat(), "end": end.isoformat(),
                                   "min_interval": self.settings.provider_min_interval_seconds,
                                   "max_attempts": self.settings.provider_max_attempts}), encoding="utf-8")
        started = dt.datetime.now(dt.timezone.utc)
        try:
            proc = subprocess.run([str(self.python), "-I", "-X", "utf8", str(BRIDGE), str(req), str(resp)],
                                  cwd=str(work), capture_output=True, timeout=self.settings.provider_timeout_seconds,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise ProviderError("PROVIDER_TIMEOUT", f"provider bridge exceeded {self.settings.provider_timeout_seconds}s") from None
        except OSError as exc:
            raise ProviderError("PROVIDER_NOT_CONFIGURED", f"cannot start provider interpreter: {exc.strerror}") from None
        finally:
            req.unlink(missing_ok=True)
        try:
            payload = json.loads(resp.read_text(encoding="utf-8")) if resp.exists() else None
        finally:
            resp.unlink(missing_ok=True)
        if payload is None:
            raise ProviderError("PROVIDER_ERROR", f"bridge exit {proc.returncode} without response; stderr tail: {(proc.stderr or '')[-300:]}")
        if not payload.get("ok"):
            raise ProviderError("PROVIDER_UNAVAILABLE", str(payload.get("fatal", "unknown bridge failure"))[:400])
        rows, errors = {}, {}
        for sym, entry in payload["results"].items():
            rows[sym] = entry.get("rows") or []
            if entry.get("error"):
                errors[sym] = entry["error"]
        meta = {"source": "kbs", "package": "vnstock", "package_version": payload.get("package_version"),
                "pandas_version": payload.get("pandas_version"), "request_start": start.isoformat(), "request_end": end.isoformat(),
                "symbols": len(symbols), "bridge_started_utc": payload.get("started_utc"),
                "bridge_finished_utc": payload.get("finished_utc"), "called_utc": started.isoformat(),
                "attempts": {s: e.get("attempts") for s, e in payload["results"].items() if e.get("attempts", 1) > 1},
                "empty": {s: e["empty_reason"] for s, e in payload["results"].items() if e.get("empty_reason")},
                "basis_note": "provider daily candles as returned; KBS applies retroactive adjustments (not total return)"}
        result = FetchResult(rows, errors, meta)
        self._cache[key] = result
        return result


class FakeProvider:
    """Deterministic in-memory provider for automated tests. Never used in REAL_PRIVATE runtime."""
    source_code = "KBS_VNSTOCK"   # mimics the configured source code so EodConfig matches in test databases
    is_real = False

    def __init__(self, data: dict[str, list[dict]] | None = None, fail_symbols: dict[str, str] | None = None,
                 raise_error: ProviderError | None = None):
        self.data = data or {}
        self.fail_symbols = fail_symbols or {}
        self.raise_error = raise_error
        self.calls: list[tuple] = []

    def fetch(self, symbols: list[str], start: dt.date, end: dt.date) -> FetchResult:
        self.calls.append((tuple(symbols), start, end))
        if self.raise_error:
            raise self.raise_error
        rows, errors = {}, {}
        for s in symbols:
            if s in self.fail_symbols:
                errors[s] = self.fail_symbols[s]
                rows[s] = []
                continue
            rows[s] = [r for r in self.data.get(s, []) if start.isoformat() <= str(r["time"])[:10] <= end.isoformat()]
        return FetchResult(rows, errors, {"source": "fake", "package": "FakeProvider", "package_version": "test",
                                          "request_start": start.isoformat(), "request_end": end.isoformat()})


def build_provider(settings: Settings) -> Provider:
    return VnstockKbsProvider(settings)
