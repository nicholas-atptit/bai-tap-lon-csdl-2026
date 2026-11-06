"""Standalone bridge executed by the user's vnstock interpreter:  <python> -I kbs_bridge.py request.json response.json

Kept free of project imports on purpose (runs with -I, outside the project venv). It only reads public daily
candles through vnstock's KBS source and writes JSON; it never touches SQL Server.
"""
import contextlib
import datetime
import io
import json
import sys
import time


def main(req_path, resp_path):
    with open(req_path, encoding="utf-8") as fh:
        req = json.load(fh)
    symbols = req["symbols"]
    start, end = req["start"], req["end"]
    min_interval = float(req.get("min_interval", 0.4))
    attempts_max = int(req.get("max_attempts", 3))
    noise = io.StringIO()
    resp = {"ok": False, "source": "kbs", "package": "vnstock", "package_version": None, "results": {},
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            import importlib.metadata as md
            from vnstock import Quote  # noqa: WPS433
        resp["package_version"] = md.version("vnstock")
        try:
            resp["pandas_version"] = md.version("pandas")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        resp["fatal"] = "IMPORT_FAILED: " + repr(exc)[:300]
        _write(resp_path, resp)
        return 3
    last_call = 0.0
    for sym in symbols:
        entry = {"rows": [], "error": None, "attempts": 0}
        for attempt in range(1, attempts_max + 1):
            wait = min_interval - (time.monotonic() - last_call)
            if wait > 0:
                time.sleep(wait)
            entry["attempts"] = attempt
            last_call = time.monotonic()
            try:
                with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                    df = Quote(source="kbs", symbol=sym).history(start=start, end=end, interval="1D")
                rows = []
                if df is not None and len(df):
                    for rec in df.to_dict("records"):
                        rows.append({k: _cell(rec[k]) for k in ("time", "open", "high", "low", "close", "volume") if k in rec})
                entry["rows"] = rows
                entry["error"] = None
                entry["columns"] = [str(c) for c in (df.columns if df is not None else [])]
                break
            except Exception as exc:  # noqa: BLE001
                empty = empty_reason(exc)
                if empty:   # the provider states it has no candle in the window (e.g. before listing): not an error
                    entry["rows"], entry["error"], entry["empty_reason"] = [], None, empty
                    break
                entry["error"] = type(exc).__name__ + ": " + str(exc)[:300]
                if attempt < attempts_max:
                    time.sleep(min(8.0, 1.0 * 2 ** (attempt - 1)))
        resp["results"][sym] = entry
    resp["ok"] = True
    resp["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _write(resp_path, resp)
    return 0


EMPTY_MARKERS = ("dữ liệu trống", "no data", "empty data")


def root_cause(exc):
    """Unwrap tenacity RetryError (vnstock retries internally) and chained causes."""
    seen = 0
    while seen < 10:
        seen += 1
        attempt = getattr(exc, "last_attempt", None)
        if attempt is not None and hasattr(attempt, "exception") and attempt.exception() is not None:
            exc = attempt.exception()
            continue
        if getattr(exc, "__cause__", None) is not None:
            exc = exc.__cause__
            continue
        break
    return exc


def empty_reason(exc):
    """Text of an explicit 'no data for this window' answer from the provider, else None (a real error)."""
    root = root_cause(exc)
    text = str(root)
    if isinstance(root, ValueError) and any(m in text.lower() for m in EMPTY_MARKERS):
        return text[:200]
    return None


def _cell(value):
    """Exact text form: timestamps as ISO, floats via shortest repr of the Python float (numpy-safe)."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, int):
        return str(int(value))
    return str(value)


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
