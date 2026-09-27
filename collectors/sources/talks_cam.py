"""S047 talks.cam: iCal нескольких публичных списков."""

import re

from ..generic import ICalCollector

LISTS = {
    5606: "Featured talks",
    5462: "Major Public Lectures in Cambridge",
    5358: "Darwin College Lecture Series",
    5769: "Cabinet of Natural History",
    23088: "CamTalks",
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
