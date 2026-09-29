"""S047 talks.cam: iCal нескольких публичных списков."""

import re

from ..generic import ICalCollector

LISTS = {   # аудит этапа 6d (scripts/talks_audit.py): публичные — 5462 и 5358; остальные — не публичные лекции
    5606: "Featured talks",                       # подборка редакции talks.cam для главной страницы
    5462: "Major Public Lectures in Cambridge",   # «open to the general public»; сейчас в ней только Darwin (Lent)
    5358: "Darwin College Lecture Series",        # пятницы Lent term (январь–март)
    5769: "Cabinet of Natural History",           # исследовательский семинар по истории естествознания
    23088: "CamTalks",                            # «ex-directory» список, семинары
}


class TalksCam(ICalCollector):
    source_id, name = "S047", "talks.cam"
    feeds = [f"https://talks.cam.ac.uk/show/ics/{i}/" for i in LISTS]

    def adjust(self, kw, feed_url):
        list_id = int(feed_url.rstrip("/").rsplit("/", 1)[-1])
        kw["categories"] = kw["categories"] + [f"talks.cam: {LISTS[list_id]}"]
        m = re.match(r"TALK(\d+)@", kw["external_id"] or "")
        if not kw["url"] and m:
            kw["url"] = f"https://talks.cam.ac.uk/talk/index/{m.group(1)}"
        return kw
