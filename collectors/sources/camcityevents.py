"""S072 Cambridge City Events: городские события (фейерверки и др.), та же платформа, что у Corn Exchange."""

from ..generic import JsonLdDetailCollector


class CamCityEvents(JsonLdDetailCollector):
    source_id, name = "S072", "Cambridge City Events"
    list_url = "https://www.camcityevents.co.uk/events"
    link_re = r'href="(https://www\.camcityevents\.co\.uk/events/[a-z0-9-]+)"'
