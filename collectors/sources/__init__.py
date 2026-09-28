"""Модули источников. ALL — порядок запуска."""

from . import (adc_camdram, beer_festival, cambridge105, cambridge_bid, cambridge_independent,
               cambridge_independent_business, cambridge_live_tickets, cambridge_news_business, grafton, grand_arcade, lion_yard,
               cambridge_news, cambridge_united, camcityevents, corn_exchange, ents24, eventbrite,
               fitzwilliam, foodies, mill_road_winter_fair, newmarket, skiddle, strawberry_fair,
               talks_cam, whatsonincambridge, towns_ents24, towns_skiddle, peterborough_united, wisbech_tc,
               peterborough_telegraph, saffron_hall, kettles_yard, newsquest,
               ucm, junction, botanic, visit_cambridge, uni_whatson, science_centre, cppf, tribe_sites,
               milton_park, family_misc)

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
    # этап 5: приоритет 2 и расширение географии
    towns_ents24.TownsEnts24(), towns_skiddle.TownsSkiddle(), peterborough_united.PeterboroughUnited(),
    wisbech_tc.WisbechTownCouncil(), peterborough_telegraph.PeterboroughTelegraph(),
    saffron_hall.SaffronHall(), kettles_yard.KettlesYard(),
    # решения после этапа 5: газеты Newsquest (RunThrough S027 отключён — национальный список, в регионе 0 событий)
    newsquest.HuntsPost(), newsquest.CambsTimes(), newsquest.WisbechStandard(), newsquest.ElyStandard(),
    # этап 6.1: HTML-источники P1 без коллектора
    ucm.UniversityMuseums(), junction.Junction(), botanic.BotanicGarden(), visit_cambridge.VisitCambridge(),
    uni_whatson.UniWhatsOn(),
    # этап 6.2: семейные источники и места
    science_centre.ScienceCentre(), family_misc.Libraries(), cppf.CambridgePPF(), tribe_sites.MuseumOfCambridge(),
    milton_park.MiltonCountryPark(), family_misc.NenePark(), family_misc.ComputingHistory(),
]
