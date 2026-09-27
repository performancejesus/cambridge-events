"""Геокодирование через postcodes.io и расчёт зоны."""

from __future__ import annotations

import math
import re

import httpx

API = "https://api.postcodes.io/postcodes"
CENTRE = (52.2053, 0.1218)  # Market Square
# Зона по расстоянию по прямой от центра — грубая замена времени в пути.
ZONES = ((3.0, "центр"), (25.0, "до 30 мин"), (60.0, "до часа"))
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$")


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def zone(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    d = km(CENTRE[0], CENTRE[1], lat, lon)
    return next((z for limit, z in ZONES if d <= limit), "дальше")


def lookup(postcodes: list[str]) -> dict[str, tuple[float, float]]:
    """Полные postcode → (lat, lon). Пачками по 100, неизвестные пропускаются."""
    full = sorted({p.upper().strip() for p in postcodes if p and POSTCODE_RE.match(p.upper().strip())})
    out: dict[str, tuple[float, float]] = {}
    with httpx.Client(timeout=30, headers={"User-Agent": "CambridgeEventsBot/0.1"}) as c:
        for i in range(0, len(full), 100):
            r = c.post(API, json={"postcodes": full[i:i + 100]})
            r.raise_for_status()
            for item in r.json()["result"]:
                res = item["result"]
                if res:
                    out[item["query"]] = (res["latitude"], res["longitude"])
    return out
