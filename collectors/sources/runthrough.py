"""S027 RunThrough: забеги (JSON-LD SportsEvent на /events). Список национальный — оставляем только события
с postcode в почтовых зонах региона (дальше зону уточнит postcodes.io)."""

import re

from ..generic import JsonLdListCollector

REGION_RE = re.compile(r"^(CB|PE|SG8|SG19|IP2[4-9]|IP3[0-3]|CM2[2-4]|CO9|CO10|MK4[0-4])\d?", re.I)


class RunThrough(JsonLdListCollector):
    source_id, name = "S027", "RunThrough"
    pages = ["https://www.runthrough.co.uk/events"]

    def keep(self, kw):
        pc = (kw.get("postcode") or "").replace(" ", "")
        return bool(REGION_RE.match(pc)) or bool(re.search(r"cambridge|newmarket|ely|huntingdon|peterborough",
                                                          f"{kw.get('venue') or ''} {kw.get('address') or ''}", re.I))
