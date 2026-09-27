"""S038 Mill Road Winter Fair: RSS новостей + дата ярмарки с главной страницы (в RSS её нет)."""

import re
from datetime import datetime

from ..base import RawEvent
from ..generic import FeedCollector
from ..http import PoliteClient

HOME = "https://www.millroadwinterfair.org/"
DATE_RE = re.compile(r"The (\d{4}) Fair will be on \w+day (\d{1,2})(?:st|nd|rd|th)? (\w+),?\s*"
                     r"(?:(\d{1,2}(?:[.:]\d{2})?\s*[ap]m)\s*(?:to|-|–)\s*(\d{1,2}(?:[.:]\d{2})?\s*[ap]m))?", re.I)


def _time(day: str, t: str | None) -> str:
    if not t:
        return day
    t = t.replace(" ", "").replace(".", ":").lower()
    fmt = "%I:%M%p" if ":" in t else "%I%p"
    return f"{day}T{datetime.strptime(t, fmt).strftime('%H:%M')}"


class MillRoadWinterFair(FeedCollector):
    source_id, name = "S038", "Mill Road Winter Fair"
    feeds = ["https://www.millroadwinterfair.org/feed/"]

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        out = super().collect(http)
        text = re.sub(r"<[^>]+>", " ", http.get(HOME).text)
        m = DATE_RE.search(re.sub(r"\s+", " ", text))
        if m:
            year, dnum, month, t1, t2 = m.groups()
            day = datetime.strptime(f"{dnum} {month} {year}", "%d %B %Y").date().isoformat()
            out.append(self.event(external_id=f"mrwf-{year}", title=f"Mill Road Winter Fair {year}", url=HOME,
                                  start=_time(day, t1), end=_time(day, t2), all_day=not t1,
                                  venue="Mill Road", address="Mill Road, Cambridge", summary=m.group(0)))
        return out
