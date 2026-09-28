"""S001 Visit Cambridge: события по разделам /event-categories/<раздел>/ (постранично; общий /whats-on/ показывает
только первые ~35). Раздел — категория события (family-friendly → тег «С детьми» по разметке сайта). Дата — со
страницы события («18th October 2026 - 18th October 2026 | 10:00 am - 4:00 pm»), postcode — из «Contact Details»."""

import re

from selectolax.parser import HTMLParser

from ..htmlevents import HtmlDetailCollector, POSTCODE_RE, find_when, meta, page_text
from ..generic import page_price

CATS = ["family-friendly", "music", "theatre", "comedy-entertainment", "art-exhibitions", "festivals", "sport"]


class VisitCambridge(HtmlDetailCollector):
    source_id, name = "S001", "Visit Cambridge"
    list_urls = [f"https://www.visitcambridge.org/event-categories/{c}/" for c in CATS]
    page_fmt = "{base}/page/{n}/"
    max_pages = 6
    link_re = r'href="(https://www\.visitcambridge\.org/event/[a-z0-9-]+/)"'

    def category_of(self, list_url: str) -> str | None:
        return list_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        text = page_text(tree.css_first("main") or tree.body)
        h1 = tree.css_first("h1")
        title = h1.text(strip=True) if h1 else meta(tree, "og:title")
        if not title or title not in text:
            return None
        scope = text[text.index(title) + len(title):]
        when = find_when(scope)
        if not when:
            return None
        start, end, t = when
        contact = scope[scope.find("Contact Details"):] if "Contact Details" in scope else ""
        contact = contact[:400]
        pc = POSTCODE_RE.search(contact)
        address = None
        if pc:   # «1 Brookside, Cambridge, Cambridgeshire CB2 1JE» — строка перед postcode
            address = re.split(r"\|", contact[:pc.end()])[-1].strip(" ,")
        return dict(title=title, start=f"{start.isoformat()}T{t}" if t else start.isoformat(),
                    end=end.isoformat() if end else None, all_day=not t, venue=None, address=address,
                    postcode=pc.group(0) if pc else None, price=page_price(page),
                    summary=(meta(tree, "og:description") or "")[:500] or None)
