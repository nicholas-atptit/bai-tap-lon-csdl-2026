"""Unit tests of the provider subprocess bridge handling (no vendor package, no network)."""
import datetime as dt
import sys
import textwrap

import pytest

from marketlab_app.config import load_settings
from marketlab_app.eod import kbs_bridge, providers
from marketlab_app.eod.providers import ProviderError, VnstockKbsProvider


def settings(**kw):
    env = {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_X", "MARKETLAB_PROVIDER_TIMEOUT_SECONDS": "10"}
    env.update(kw)
    return load_settings(env=env)


def test_not_configured():
    with pytest.raises(ProviderError) as e:
        VnstockKbsProvider(settings())
    assert e.value.code == "PROVIDER_NOT_CONFIGURED"
    with pytest.raises(ProviderError) as e:
        VnstockKbsProvider(settings(MARKETLAB_PROVIDER_PYTHON=r"C:\nope\python.exe"))
    assert e.value.code == "PROVIDER_NOT_CONFIGURED"


def _with_bridge(monkeypatch, tmp_path, body: str):
    script = tmp_path / "bridge.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.setattr(providers, "BRIDGE", script)
    return VnstockKbsProvider(settings(MARKETLAB_PROVIDER_PYTHON=sys.executable))


def test_timeout_kills_bridge(monkeypatch, tmp_path):
    p = _with_bridge(monkeypatch, tmp_path, "import time; time.sleep(30)")
    with pytest.raises(ProviderError) as e:
        p.fetch(["ACB"], dt.date(2026, 11, 3), dt.date(2026, 11, 4))
    assert e.value.code == "PROVIDER_TIMEOUT"


def test_bridge_without_response(monkeypatch, tmp_path):
    p = _with_bridge(monkeypatch, tmp_path, "import sys; sys.exit(5)")
    with pytest.raises(ProviderError) as e:
        p.fetch(["ACB"], dt.date(2026, 11, 3), dt.date(2026, 11, 4))
    assert e.value.code == "PROVIDER_ERROR"


def test_vendor_import_failure_is_unavailable(monkeypatch, tmp_path):
    p = _with_bridge(monkeypatch, tmp_path, """
        import json, sys
        json.dump({"ok": False, "fatal": "IMPORT_FAILED: ModuleNotFoundError('vnstock')"}, open(sys.argv[2], "w"))
    """)
    with pytest.raises(ProviderError) as e:
        p.fetch(["ACB"], dt.date(2026, 11, 3), dt.date(2026, 11, 4))
    assert e.value.code == "PROVIDER_UNAVAILABLE"


def test_per_symbol_errors_and_rows_are_returned(monkeypatch, tmp_path):
    p = _with_bridge(monkeypatch, tmp_path, """
        import json, sys
        json.dump({"ok": True, "package_version": "9.9", "results": {
            "ACB": {"rows": [{"time": "2026-11-04T07:00:00", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "5"}], "error": None, "attempts": 1},
            "BAD": {"rows": [], "error": "ConnectionError: reset", "attempts": 3}}}, open(sys.argv[2], "w"))
    """)
    res = p.fetch(["ACB", "BAD"], dt.date(2026, 11, 3), dt.date(2026, 11, 4))
    assert res.rows["ACB"][0]["close"] == "1" and res.errors == {"BAD": "ConnectionError: reset"}
    assert res.meta["package_version"] == "9.9" and res.meta["attempts"] == {"BAD": 3}


def test_bridge_cell_formatting_is_exact():
    class Num(float):
        pass
    assert kbs_bridge._cell(Num(21.56)) == "21.56"
    assert kbs_bridge._cell(dt.datetime(2026, 11, 4, 7)) == "2026-11-04T07:00:00"
    assert kbs_bridge._cell(12) == "12"
