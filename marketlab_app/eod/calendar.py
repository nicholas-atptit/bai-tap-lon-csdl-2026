"""Session decisions in Asia/Ho_Chi_Minh, based on a provider reference series (evidence), not on guesses."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .normalize import VN_TZ


@dataclass(frozen=True)
class Decision:
    kind: str                 # SESSION | NO_SESSION | SKIPPED
    code: str                 # e.g. PROVIDER_SESSION, WEEKEND, PROVIDER_CALENDAR_GAP, BEFORE_CUTOFF ...
    message: str
    evidence: dict = field(default_factory=dict)


def now_vn(clock: dt.datetime | None = None) -> dt.datetime:
    value = clock or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise ValueError("clock must be timezone-aware")
    return value.astimezone(VN_TZ)


def parse_cutoff(text: str) -> dt.time:
    h, m = text.split(":")
    return dt.time(int(h), int(m))


def default_session_date(clock: dt.datetime | None = None) -> dt.date:
    """'Today' for the scheduler is the calendar date in Vietnam, never the UTC date."""
    return now_vn(clock).date()


def precheck(session: dt.date, clock: dt.datetime | None, cutoff: str) -> Decision | None:
    local = now_vn(clock)
    today = local.date()
    if session > today:
        return Decision("SKIPPED", "FUTURE_DATE", f"{session} is after today {today} (Asia/Ho_Chi_Minh)")
    if session == today and local.time() < parse_cutoff(cutoff):
        return Decision("SKIPPED", "BEFORE_CUTOFF",
                        f"now {local:%H:%M} < configured cutoff {cutoff} (Asia/Ho_Chi_Minh); cutoff is a scheduling setting, not proof of finalized data")
    if session.weekday() >= 5:
        return Decision("NO_SESSION", "WEEKEND", f"{session} is a {session:%A}")
    return None


def classify(session: dt.date, reference_dates: set[dt.date], reference_symbol: str) -> Decision:
    """Use the provider's reference series (e.g. VN30 index candles) as calendar evidence."""
    before = max((d for d in reference_dates if d < session), default=None)
    after = min((d for d in reference_dates if d > session), default=None)
    ev = {"reference_symbol": reference_symbol, "previous_reference_candle": before.isoformat() if before else None,
          "next_reference_candle": after.isoformat() if after else None}
    if session in reference_dates:
        return Decision("SESSION", "PROVIDER_SESSION", f"{reference_symbol} has a candle on {session}", ev)
    if after is not None:
        return Decision("NO_SESSION", "PROVIDER_CALENDAR_GAP",
                        f"{reference_symbol} has candles on {before} and {after} but not on {session}: non-trading weekday (holiday/closure) per provider",
                        ev)
    return Decision("SKIPPED", "DATA_NOT_YET_AVAILABLE",
                    f"no {reference_symbol} candle on {session} and none after it yet: data late or not a session; retry later",
                    ev)
