"""Unit: pure backfill rules (no SQL Server, no network)."""
import datetime as dt
from decimal import Decimal

import pytest

from marketlab_app.config import HISTORY_FLOOR, ConfigError, load_settings
from marketlab_app.eod import backfill as bf
from marketlab_app.eod.normalize import VN_TZ, Candle
from marketlab_app.eod.providers import FakeProvider

D = dt.date


def test_year_chunks_split_on_calendar_years():
    assert bf.year_chunks(D(2023, 1, 1), D(2023, 3, 1)) == [(D(2023, 1, 1), D(2023, 3, 1))]
    assert bf.year_chunks(D(2023, 1, 1), D(2026, 11, 5)) == [
        (D(2023, 1, 1), D(2023, 12, 31)), (D(2024, 1, 1), D(2024, 12, 31)), (D(2025, 1, 1), D(2025, 12, 31)), (D(2026, 1, 1), D(2026, 11, 5))]


@pytest.mark.parametrize("local,expected", [
    (dt.datetime(2026, 11, 6, 10, 27), D(2026, 11, 5)),    # trading hours: today's candle is provisional
    (dt.datetime(2026, 11, 6, 16, 10), D(2026, 11, 6)),    # at the cutoff
    (dt.datetime(2026, 11, 8, 12, 0), D(2026, 11, 6)),     # Sunday -> Friday
    (dt.datetime(2026, 11, 9, 9, 0), D(2026, 11, 6)),      # Monday morning -> Friday
])
def test_completed_candidate_uses_vietnam_time_and_cutoff(local, expected):
    assert bf.completed_candidate(local.replace(tzinfo=VN_TZ), "16:10") == expected


def test_completed_candidate_converts_from_utc():
    # 2026-11-06 01:00 UTC = 08:00 in Vietnam: the 2026-11-06 session is not complete
    assert bf.completed_candidate(dt.datetime(2026, 11, 6, 1, 0, tzinfo=dt.timezone.utc), "16:10") == D(2026, 11, 5)


def test_latest_completed_session_skips_provider_holidays():
    ref = {D(2026, 4, 24), D(2026, 4, 28), D(2026, 5, 4)}          # 27/4, 30/4, 1/5 closed
    assert bf.latest_completed_session(ref, D(2026, 5, 1)) == D(2026, 4, 28)
    assert bf.latest_completed_session(ref, D(2026, 4, 23)) is None


def _c(t, d):
    return Candle(t, d, Decimal(1), Decimal(1), Decimal(1), Decimal(1), 1)


def test_classify_session_distinguishes_missing_no_history_and_rejected():
    s = D(2025, 3, 3)
    staged = {"AAA": {s: _c("AAA", s)}, "NEW": {D(2025, 5, 13): _c("NEW", D(2025, 5, 13))}, "GAP": {D(2025, 1, 2): _c("GAP", D(2025, 1, 2))},
              "BAD": {D(2025, 1, 2): _c("BAD", D(2025, 1, 2))}, "ERR": {}}
    first = {t: (min(v) if v else None) for t, v in staged.items()}
    ok_through = {"AAA": D(2025, 12, 31), "NEW": D(2025, 12, 31), "GAP": D(2025, 12, 31), "BAD": D(2025, 12, 31), "ERR": None}
    out = bf.classify_session(s, list(staged), staged, first, ok_through, {"BAD": {s}})
    assert out == {"AAA": "PRESENT", "NEW": "NO_HISTORY", "GAP": "MISSING", "BAD": "REJECTED_ROW", "ERR": "MISSING"}


def test_no_history_requires_successful_fetch_up_to_the_session():
    s = D(2024, 6, 3)
    staged = {"NEW": {D(2025, 5, 13): _c("NEW", D(2025, 5, 13))}}
    # 2024 chunk failed -> we cannot claim the provider has no history: MISSING
    assert bf.classify_session(s, ["NEW"], staged, {"NEW": D(2025, 5, 13)}, {"NEW": D(2023, 12, 31)}, {}) == {"NEW": "MISSING"}


def test_history_floor_cannot_move_earlier_than_2023():
    assert HISTORY_FLOOR == D(2023, 1, 1)
    base = {"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Live"}
    assert load_settings(env=base).history_start == D(2023, 1, 1)
    assert load_settings(env={**base, "MARKETLAB_HISTORY_START": "2024-01-01"}).history_start == D(2024, 1, 1)
    with pytest.raises(ConfigError):
        load_settings(env={**base, "MARKETLAB_HISTORY_START": "2022-12-31"})


def test_resolve_latest_end_date_from_provider_calendar():
    s = load_settings(env={"MARKETLAB_MODE": "REAL_PRIVATE", "MARKETLAB_SQL_DATABASE": "MarketLabVN30_Live"})
    days = [D(2026, 10, 30), D(2026, 11, 2), D(2026, 11, 3), D(2026, 11, 5), D(2026, 11, 6)]   # 4/11 closed; 6/11 provisional
    p = FakeProvider({"VN30": [{"time": f"{d}T07:00:00", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"} for d in days]})
    cfg = {"CutoffLocalTime": "16:10:00", "CalendarReferenceSymbol": "VN30"}
    morning = bf.BackfillService(s, provider=p, clock=dt.datetime(2026, 11, 6, 10, 27, tzinfo=VN_TZ))
    assert morning._resolve_end(cfg, "latest") == D(2026, 11, 5)
    late = bf.BackfillService(s, provider=p, clock=dt.datetime(2026, 11, 5, 9, 0, tzinfo=VN_TZ))
    assert late._resolve_end(cfg, "latest") == D(2026, 11, 3)        # 5/11 before cutoff, 4/11 not a session
    with pytest.raises(bf.BackfillError) as e:
        morning._resolve_end(cfg, "2026-11-06")
    assert e.value.code == "END_NOT_COMPLETED"
