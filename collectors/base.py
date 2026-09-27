"""Общий интерфейс коллекторов и единый формат сырого события."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .http import PoliteClient


@dataclass
class RawEvent:
    source_id: str                 # ID из реестра, например "S005"
    title: str
    url: str | None                # страница события у первоисточника
    kind: str = "event"            # "event" — событие с датой; "article" — запись фида (новость, пост)
    external_id: str | None = None # ID у источника (UID из iCal, id из API, URL)
    start: str | None = None       # ISO 8601; дата без времени — "YYYY-MM-DD"
    end: str | None = None
    all_day: bool = False
    venue: str | None = None
    address: str | None = None
    postcode: str | None = None
    lat: float | None = None
    lon: float | None = None
    price: str | None = None       # как у источника: "£5.00 – £25.00", "Free"
    status: str | None = None      # scheduled / cancelled / postponed / rescheduled / sold_out
    organizer: str | None = None
    categories: list[str] = field(default_factory=list)
    summary: str | None = None     # короткий фрагмент описания для внутреннего использования (не публикуется)
    published: str | None = None   # для статей: дата публикации
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)


class Collector:
    """Базовый класс. Наследник задаёт source_id, name и реализует collect()."""

    source_id: str = ""
    name: str = ""

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        raise NotImplementedError

    def event(self, **kw) -> RawEvent:
        return RawEvent(source_id=self.source_id, **kw)
