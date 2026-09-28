"""Нормализация: названия, площадки, цены, дата/время."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

# Слова, которые не отличают одно событие от другого.
TITLE_NOISE = {
    "the", "a", "an", "and", "live", "tour", "tickets", "ticket", "presents", "present", "in", "at", "concert",
    "show", "uk", "cambridge", "official", "with", "of", "event", "night", "evening", "2026", "2027", "2028",
}
VENUE_NOISE = {"the", "cambridge", "england", "uk", "theatre", "hall", "cb", "ltd", "centre", "center"}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().replace("&", " and ")


def norm_title(title: str) -> str:
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", _ascii(title))          # скобки: (3-0), [EFLT], (sold out)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w not in TITLE_NOISE)


def title_similarity(a: str, b: str) -> float:
    """0..1. Учитывает перестановки и вложенность («Artist: Show» ≈ «Show»)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    if a == b:
        return 1.0
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    containment = len(small & big) / len(small)
    if containment == 1.0 and len(small) >= 2:
        return 0.95
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    jacc = len(ta & tb) / len(ta | tb)
    return max(seq * 0.9, jacc, containment * 0.85 if len(small) >= 3 else 0)


def norm_venue(name: str | None) -> str:
    if not name:
        return ""
    s = _ascii(name.split(",")[0])
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w not in VENUE_NOISE)


# --- цены ---
FREE_RE = re.compile(r"\b(free (entry|admission|event|to attend|of charge|and open to all)|admission (is )?free|entry (is )?free|no charge)\b", re.I)
PRICE_RE = re.compile(r"(?:£|GBP\s?)(\d+(?:[.,]\d{1,2})?)")


def parse_price(price_text: str | None, *free_text: str | None) -> float | None:
    """Минимальная цена в фунтах; 0 — бесплатно; None — неизвестно."""
    if price_text:
        t = price_text.strip().lower()
        if t in ("free", "0", "£0", "gbp 0", "0.00", "£0.00", "gbp 0.00") or t.startswith("free"):
            return 0.0
        nums = [float(n.replace(",", ".")) for n in PRICE_RE.findall(price_text)]
        if not nums:
            nums = [float(n) for n in re.findall(r"\b(\d+(?:\.\d{1,2})?)\b", price_text)]
        if nums:
            return min(nums)
    for t in free_text:
        if t and FREE_RE.search(t):
            return 0.0
    return None


# --- дата и время ---

def split_datetime(value: str | None) -> tuple[str | None, str | None]:
    """ISO-строка → (дата, время) по Лондону. Дата без времени → (дата, None)."""
    if not value:
        return None, None
    v = value.strip()
    if len(v) == 10:
        return v, None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return v[:10], None
    if dt.tzinfo:
        dt = dt.astimezone(LONDON)
    t = dt.strftime("%H:%M")
    return dt.date().isoformat(), (None if t == "00:00" and "T00:00" in v else t)


def end_date(start: str | None, end: str | None) -> str | None:
    """Дата окончания с поправкой на однодневные события: окончание на следующий день до 06:00 (вечеринка
    до утра, «весь день» 00:00–23:59:59 UTC у Cambridge 105 → 01:00–00:59 по Лондону) — тот же день."""
    ds, _ = split_datetime(start)
    de, te = split_datetime(end)
    if not ds or not de:
        return de
    if te and te < "06:00" and date.fromisoformat(de) == date.fromisoformat(ds) + timedelta(days=1):
        return ds
    return de


def minutes(t: str | None) -> int | None:
    if not t:
        return None
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)
