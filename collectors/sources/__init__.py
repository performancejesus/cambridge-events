"""Модули источников. ALL — порядок запуска."""

from . import (adc_camdram, beer_festival, cambridge105, cambridge_bid, cambridge_independent,
               cambridge_independent_business, cambridge_live_tickets, cambridge_news_business, grafton, grand_arcade, lion_yard,
               cambridge_news, cambridge_united, camcityevents, corn_exchange, ents24, eventbrite,
               fitzwilliam, foodies, mill_road_winter_fair, newmarket, skiddle, strawberry_fair,
               talks_cam, whatsonincambridge)

ALL = [
    cambridge105.Cambridge105(), talks_cam.TalksCam(), adc_camdram.AdcCamdram(),
    cambridge_united.CambridgeUnited(), beer_festival.BeerFestival(),
    cambridge_independent.CambridgeIndependent(), cambridge_news.CambridgeNews(),
    whatsonincambridge.WhatsOnInCambridge(), foodies.CambridgeFoodies(), fitzwilliam.Fitzwilliam(),
    mill_road_winter_fair.MillRoadWinterFair(), ents24.Ents24(), skiddle.Skiddle(), newmarket.Newmarket(),
    corn_exchange.CornExchange(), strawberry_fair.StrawberryFair(), camcityevents.CamCityEvents(),
    eventbrite.Eventbrite(), cambridge_live_tickets.CambridgeLiveTickets(),
    cambridge_independent_business.CambridgeIndependentBusiness(), cambridge_news_business.CambridgeNewsBusiness(),
    grand_arcade.GrandArcade(), lion_yard.LionYard(), grafton.Grafton(), cambridge_bid.CambridgeBid(),
]
