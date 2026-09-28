"""S108 Wisbech Town Council: iCal календаря совета — городские события (иллюминация, ярмарки), без заседаний."""

import re

from ..generic import ICalCollector

MEETING_RE = re.compile(r"committee|council\b|meeting|agenda|^planning", re.I)


class WisbechTownCouncil(ICalCollector):
    source_id, name = "S108", "Wisbech Town Council"
    feeds = ["https://www.wisbechtowncouncil.gov.uk/feeds/ical/638856?nodeid=2929"]

    def collect(self, http):
        return [e for e in super().collect(http) if not MEETING_RE.search(e.title)]

    def adjust(self, kw, feed_url):
        if kw.get("venue") and "wisbech" not in (kw.get("address") or "").lower():
            kw["address"] = f"{kw['address'].strip()}, Wisbech"
        kw["url"] = kw["url"] or "https://www.wisbechtowncouncil.gov.uk/local-events"
        return kw
