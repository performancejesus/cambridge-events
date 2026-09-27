"""S032 Cambridge Beer Festival: iCal The Events Calendar."""

from ..generic import ICalCollector


class BeerFestival(ICalCollector):
    source_id, name = "S032", "Cambridge Beer Festival"
    feeds = ["https://www.cambridgebeerfestival.com/events/?ical=1"]
