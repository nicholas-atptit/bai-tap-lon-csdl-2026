"""Provider OHLCV -> validated candles. Pure functions (unit-tested without SQL or network)."""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_DECIMALS = 6           # dbo.DailyPrice decimal(19,6)
MAX_INTEGER_DIGITS = 13    # 19 - 6
MAX_VOLUME = 9_223_372_036_854_775_807
# KBS (via vnstock) labels a daily candle with a naive timestamp at 07:00 (= 00:00 UTC shown in UTC+7) or 00:00.
ACCEPTED_NAIVE_HOURS = {0, 7}


class ValidationIssue(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Candle:
    ticker: str
    trade_date: dt.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def values(self) -> tuple:
        return (self.open, self.high, self.low, self.close, self.volume)

    def as_payload(self, stock_id: int) -> dict:
        return {"StockId": stock_id, "Open": format(self.open, "f"), "High": format(self.high, "f"),
                "Low": format(self.low, "f"), "Close": format(self.close, "f"), "Volume": str(self.volume)}


def parse_trade_date(raw: object) -> dt.date:
    """Calendar date of a daily candle in Asia/Ho_Chi_Minh. Never shifts a date through UTC."""
    if isinstance(raw, dt.datetime):
        value = raw
    elif isinstance(raw, dt.date):
        return raw
    elif isinstance(raw, str):
        text = raw.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return dt.date.fromisoformat(text)
        try:
            value = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationIssue("BAD_TIME_FORMAT", f"unparseable candle time {text[:40]!r}") from exc
    else:
        raise ValidationIssue("BAD_TIME_FORMAT", f"unsupported candle time type {type(raw).__name__}")
    if value.tzinfo is not None:
        return value.astimezone(VN_TZ).date()
    if value.hour in ACCEPTED_NAIVE_HOURS and value.minute == 0 and value.second == 0 and value.microsecond == 0:
        return value.date()
    raise ValidationIssue("BAD_TIME_FORMAT", f"naive intraday timestamp {value.isoformat()} is not a daily candle label")


def to_price(raw: object, field: str) -> Decimal:
    if isinstance(raw, bool) or raw is None:
        raise ValidationIssue("BAD_NUMBER", f"{field} missing")
    if isinstance(raw, float):
        if not math.isfinite(raw):
            raise ValidationIssue("NOT_FINITE", f"{field}={raw}")
        text = repr(raw)
    else:
        text = str(raw).strip()
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationIssue("BAD_NUMBER", f"{field}={text[:30]!r}") from exc
    if not value.is_finite():
        raise ValidationIssue("NOT_FINITE", f"{field}={text}")
    if value <= 0:
        raise ValidationIssue("NON_POSITIVE_PRICE", f"{field}={text}")
    exponent = value.normalize().as_tuple().exponent
    if isinstance(exponent, int) and -exponent > MAX_DECIMALS:
        raise ValidationIssue("PRECISION", f"{field}={text} has more than {MAX_DECIMALS} decimals")
    if value >= Decimal(10) ** MAX_INTEGER_DIGITS:
        raise ValidationIssue("PRECISION", f"{field}={text} exceeds decimal(19,6)")
    return value


def to_volume(raw: object) -> int:
    if isinstance(raw, bool) or raw is None:
        raise ValidationIssue("BAD_VOLUME", "volume missing")
    if isinstance(raw, float):
        if not math.isfinite(raw) or raw != int(raw):
            raise ValidationIssue("BAD_VOLUME", f"volume={raw} is not an integer")
        raw = int(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not re.fullmatch(r"-?\d+(\.0+)?", text):
            raise ValidationIssue("BAD_VOLUME", f"volume={text[:30]!r} is not an integer")
        raw = int(Decimal(text))
    if not isinstance(raw, int):
        raise ValidationIssue("BAD_VOLUME", f"volume type {type(raw).__name__}")
    if raw < 0 or raw > MAX_VOLUME:
        raise ValidationIssue("BAD_VOLUME", f"volume={raw} out of range")
    return raw


def validate_candle(ticker: str, raw: dict) -> Candle:
    o, h = to_price(raw.get("open"), "open"), to_price(raw.get("high"), "high")
    lo, c = to_price(raw.get("low"), "low"), to_price(raw.get("close"), "close")
    v = to_volume(raw.get("volume"))
    if h < max(o, c, lo):
        raise ValidationIssue("OHLC_RANGE", f"high {h} < max(open,close,low)")
    if lo > min(o, c, h):
        raise ValidationIssue("OHLC_RANGE", f"low {lo} > min(open,close,high)")
    return Candle(ticker, parse_trade_date(raw.get("time")), o, h, lo, c, v)


def normalize_series(ticker: str, raw_rows: list[dict]) -> tuple[dict[dt.date, Candle], list[str]]:
    """Validate every row; identical duplicates collapse (noted), conflicting duplicates raise."""
    out: dict[dt.date, Candle] = {}
    notes: list[str] = []
    for raw in raw_rows:
        candle = validate_candle(ticker, raw)
        prev = out.get(candle.trade_date)
        if prev is not None:
            if prev.values() != candle.values():
                raise ValidationIssue("SOURCE_DUPLICATE_CONFLICT", f"{ticker} {candle.trade_date} has two different candles")
            notes.append(f"{ticker} {candle.trade_date}: identical duplicate collapsed")
            continue
        out[candle.trade_date] = candle
    return out, notes
