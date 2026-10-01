"""Правки по v8: общий глоссарий перевода для выпуска (prompts/issue.md) и строк «Каникул» / полного списка программ
(pipeline/kids_collect.TEXT_PROMPT). Названия программ переводим по смыслу, а не по словарю: «Junior gym (11–17)» —
тренажёрный зал для подростков, а не «гимнастика для младших»."""

GLOSSARY = """Translation glossary (English → Russian), use it for titles and descriptions:
- gym, junior gym, gym session, fitness suite — a room with fitness equipment → тренажёрный зал (junior gym for 11–17 →
  «тренажёрный зал для подростков»); gymnastics, a gymnastics club or academy (Gymfinity, gymnastics camp) → гимнастика
  («каникулярный лагерь гимнастики»), never «тренажёрный зал»; trampolining → занятия на батуте;
- multi-sports, multi-activity → мультиспорт / разные виды спорта; holiday camp → каникулярный лагерь;
  holiday club → каникулярный клуб; half term → каникулы; soft play → игровая комната;
- swimming lessons → уроки плавания; fun session, splash session → свободное плавание;
- forest school → лесная школа; STEM → научно-технические занятия; coding → программирование;
- junior (in club and sport names) → для детей / для подростков по возрасту из данных, never «младший»;
- performing arts, drama → театральная студия; dance → танцы; climbing, bouldering → скалолазание;
- tennis camp → теннисный лагерь; football camp → футбольный лагерь; cricket → крикет; rugby → регби;
- towns: Bury St Edmunds → Бери-Сент-Эдмундс, Saffron Walden → Саффрон-Уолден, St Ives → Сент-Айвс,
  St Neots → Сент-Нитс, Huntingdon → Хантингдон, Peterborough → Питерборо, Ely → Эли, Newmarket → Ньюмаркет;
- family fun day → семейный праздник; storytime, rhymetime → чтение вслух / стишки и песенки для малышей;
- cultural realities (этап 7e, правки по v11) — never replace a British custom with a Russian one:
  Father Christmas, Santa → Father Christmas or «Санта» (never «Дед Мороз»); grotto → «грот Санты»;
  pantomime, panto → «пантомима (рождественское семейное шоу)» at the first mention;
  Bonfire Night, Guy Fawkes Night → «Bonfire Night (ночь костров и фейерверков, 5 ноября)» at the first mention;
  half term → «школьные каникулы (half term)» at the first mention; trick or treat → «trick or treat» (сбор сладостей);
  carol service → «рождественская служба с гимнами»; Christmas market → рождественская ярмарка."""

# Этап 7e (правки по v11): культурные реалии — исправление без модели и проверка 45.
REALIA_FIXES = [   # (регулярное выражение в русском тексте, замена)
    (r"\bДед(?:ушк)?а Мороза\b", "Санту"), (r"\bДед(?:ушк)?у Морозу\b", "Санте"), (r"\bДед(?:ушк)?ом Морозом\b", "Сантой"),
    (r"\bДед(?:ушк)?е Морозе\b", "Санте"), (r"\bДед(?:ушка)? Мороз\b", "Санта"),
]
REALIA_EXPLAIN = [   # (признак в данных, слово в русском тексте, пояснение при первом упоминании)
    (r"\bpanto(?:mime)?\b", r"пантомим\w*", "рождественское семейное шоу"),
    (r"\bbonfire night|guy fawkes\b", r"ночь костров|bonfire night", "5 ноября: костры и фейерверки"),
]


def realia_ru(text: str) -> str:
    """Замена «Деда Мороза» на «Санту» (Father Christmas — британская реалия) в любом русском тексте."""
    import re
    for rx, good in REALIA_FIXES:
        text = re.sub(rx, good, text)
    return text
