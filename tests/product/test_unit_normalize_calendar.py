"""Unit tests: OHLCV normalization, dates/timezone, sessions, config. No SQL, no network."""
import datetime as dt
from decimal import Decimal

import pytest

from marketlab_app.config import ConfigError, load_settings
from marketlab_app.eod.calendar import classify, default_session_date, precheck
from marketlab_app.eod.normalize import VN_TZ, ValidationIssue, normalize_series, parse_trade_date, to_price, to_volume, validate_candle

GOOD = {"time": "2026-11-04T07:00:00", "open": "20.3", "high": "20.55", "low": "20.15", "close": "20.5", "volume": "11819700"}


def test_valid_candle_keeps_exact_decimals():
    c = validate_candle("ACB", GOOD)
    assert c.trade_date == dt.date(2026, 11, 4)
    assert c.close == Decimal("20.5") and c.volume == 11819700
    assert c.as_payload(1) == {"StockId": 1, "Open": "20.3", "High": "20.55", "Low": "20.15", "Close": "20.5", "Volume": "11819700"}


def test_integer_price_never_formatted_in_exponent_notation():
    c = validate_candle("X", {**GOOD, "open": "100", "high": "100", "low": "100", "close": "100"})
    assert c.as_payload(1)["Close"] == "100"


@pytest.mark.parametrize("field,value,code", [
    ("open", "0", "NON_POSITIVE_PRICE"), ("close", "-1", "NON_POSITIVE_PRICE"), ("high", "nan", "NOT_FINITE"),
    ("low", float("inf"), "NOT_FINITE"), ("close", "abc", "BAD_NUMBER"), ("open", None, "BAD_NUMBER"),
    ("close", "20.1234567", "PRECISION"), ("close", "99999999999999", "PRECISION"),
    ("volume", "-5", "BAD_VOLUME"), ("volume", "10.5", "BAD_VOLUME"), ("volume", 12.25, "BAD_VOLUME"), ("volume", True, "BAD_VOLUME"),
])
def test_invalid_values_rejected(field, value, code):
    with pytest.raises(ValidationIssue) as e:
        validate_candle("X", {**GOOD, field: value})
    assert e.value.code == code


@pytest.mark.parametrize("patch", [{"high": "20.4"}, {"high": "20.2"}, {"low": "20.4"}, {"low": "20.6"}])
def test_ohlc_relations(patch):
    with pytest.raises(ValidationIssue) as e:
        validate_candle("X", {**GOOD, **patch})
    assert e.value.code == "OHLC_RANGE"


def test_float_inputs_use_shortest_repr():
    assert to_price(21.56, "close") == Decimal("21.56")
    assert to_volume(1000.0) == 1000


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-04", dt.date(2026, 11, 4)),
    ("2026-11-04T07:00:00", dt.date(2026, 11, 4)),           # KBS naive label (00:00 UTC rendered at +07)
    ("2026-11-04 00:00:00", dt.date(2026, 11, 4)),
    ("2026-11-03T17:00:00+00:00", dt.date(2026, 11, 4)),     # aware UTC -> Vietnam calendar date
    ("2026-11-04T00:00:00+07:00", dt.date(2026, 11, 4)),
])
def test_trade_date_parsing_respects_vietnam_timezone(raw, expected):
    assert parse_trade_date(raw) == expected


def test_naive_intraday_timestamp_rejected():
    with pytest.raises(ValidationIssue):
        parse_trade_date("2026-11-04T14:45:00")


def test_identical_duplicate_collapses_conflicting_duplicate_raises():
    series, notes = normalize_series("X", [GOOD, dict(GOOD)])
    assert len(series) == 1 and notes
    with pytest.raises(ValidationIssue) as e:
        normalize_series("X", [GOOD, {**GOOD, "close": "20.45"}])
    assert e.value.code == "SOURCE_DUPLICATE_CONFLICT"


def test_session_date_uses_vietnam_not_utc():
    # 2026-11-05 18:30 UTC is already 2026-11-06 01:30 in Vietnam
    assert default_session_date(dt.datetime(2026, 11, 5, 18, 30, tzinfo=dt.timezone.utc)) == dt.date(2026, 11, 6)


def test_precheck_future_cutoff_weekend():
    clock = dt.datetime(2026, 11, 5, 15, 0, tzinfo=VN_TZ)
    assert precheck(dt.date(2026, 11, 6), clock, "16:10").code == "FUTURE_DATE"
    assert precheck(dt.date(2026, 11, 5), clock, "16:10").code == "BEFORE_CUTOFF"
    assert precheck(dt.date(2026, 11, 1), clock, "16:10").kind == "NO_SESSION"
    assert precheck(dt.date(2026, 11, 4), clock, "16:10") is None
    assert precheck(dt.date(2026, 11, 5), dt.datetime(2026, 11, 5, 16, 10, tzinfo=VN_TZ), "16:10") is None


def test_classify_with_provider_reference():
    ref = {dt.date(2026, 8, 28), dt.date(2026, 9, 3)}
    assert classify(dt.date(2026, 9, 3), ref, "VN30").kind == "SESSION"
    hol = classify(dt.date(2026, 9, 1), ref, "VN30")
    assert hol.kind == "NO_SESSION" and hol.code == "PROVIDER_CALENDAR_GAP"
    assert hol.evidence["previous_reference_candle"] == "2026-08-28" and hol.evidence["next_reference_candle"] == "2026-09-03"
    late = classify(dt.date(2026, 9, 4), ref, "VN30")
    assert late.kind == "SKIPPED" and late.code == "DATA_NOT_YET_AVAILABLE"


def test_config_validation_and_redaction():
    s = load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Live",
                           "MARKETLAB_SQL_AUTH": "sql", "MARKETLAB_SQL_USER": "u", "MARKETLAB_SQL_PASSWORD": "S3cret!pw",
                           "MARKETLAB_OPS_TOKEN": "x" * 40})
    red = s.redacted()
    assert "S3cret" not in repr(s) and "S3cret" not in str(red) and "x" * 40 not in str(red)
    for bad in ({"MARKETLAB_MODE": "PROD"}, {"MARKETLAB_MODE": "REAL_PRIVATE"},
                {"MARKETLAB_HOST": "0.0.0.0"}, {"MARKETLAB_OPS_TOKEN": "short"},
                {"MARKETLAB_SQL_DATABASE": "x;DROP"}, {"MARKETLAB_SQL_AUTH": "sql"}, {"MARKETLAB_EOD_CUTOFF": "25:00"}):
        with pytest.raises(ConfigError):
            load_settings(env=bad)
    assert load_settings(env={}).sql_database == "MarketLabVN30_Demo"
