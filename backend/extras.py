"""Additive helpers for Issues 7-19: IST time, activity log, lead-employee master, work-done, CSV."""
import io
import csv
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def ist_today_str():
    return datetime.now(IST).date().isoformat()


def ist_day_bounds(date_str):
    """Return (start_utc_iso, end_utc_iso) covering the IST day for date_str (YYYY-MM-DD)."""
    d = datetime.fromisoformat(date_str).date()
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def to_csv(headers, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()
