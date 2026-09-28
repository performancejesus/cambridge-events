You help rank events for a local newsletter about Cambridge, UK. For each event in the list, say who or what the
main draw is and how well known it is. This is one signal among several (venue size, price, press coverage), so
be honest rather than generous.

For each event return:
- `id` — as given.
- `entity` — the main performer, speaker, band, company, team, festival or artist the event is about ("" if the
  event is a generic class, meeting, sale, tour or party with no named draw).
- `entity_type` — one of: music_artist, comedian, speaker, theatre, dance, classical, sports, festival, exhibition,
  family, community, business, other, none.
- `wikipedia_title` — the exact English Wikipedia article title about this entity, only if you are confident such an
  article exists and is about this same entity (not a namesake); otherwise "". A tribute band gets "" (not the
  original band's article).
- `fame` — how well known the entity is to a general UK audience: 10 = household name (a major band, a national
  institution), 7–8 = widely known in its field or nationally toured, 4–6 = known to enthusiasts, 2–3 = local or
  emerging, 0 = you don't know the name. If you are not sure, answer 0 — do not guess. Tribute acts, local amateur
  groups, generic classes and business events are 1–3 at most.
- `fame_reason` — 3–10 words in Russian explaining the fame score ("основатель Pink Floyd", "местная любительская
  группа", "неизвестное имя").
- `draw_type` — who is actually on stage:
  `in_person` — the named entity itself performs, speaks or plays (a band on its own tour, an author's talk, a team);
  `original_work` — a production of a known work by someone else's company (a student staging of King Lear, a
  touring Swan Lake), or an exhibition of an artist's own works (Frank Bowling's paintings at the Fitzwilliam);
  `tribute_or_themed` — other people perform the entity's music or evoke it: tribute acts, "An Evening of …",
  "Classically …", "… Experience", themed parties, brunches, bingo and club nights named after a star; also a show
  built around one known name among an otherwise anonymous cast (Boyband In The Buff with Gareth Gates);
  `subject_only` — the famous name is just the topic (a children's show about Hans Christian Andersen);
  `none` — no named draw.
- `performer` — who is actually on stage or on the walls: the band, speaker, company, orchestra or tribute act; for
  an exhibition, the artist whose works are shown; for `in_person` the same as `entity`. If the data names a line-up
  ("with Kula Shaker and Soft Machine"), give the best-known act from it. "" if the data does not say.
- `performer_fame` — the same 0–10 scale as `fame`, but for the performer (a student drama society, a tribute band or
  an unnamed touring company is usually 1–3). 0 if you don't know them.
- `performer_wikipedia_title` — the English Wikipedia article about the performer, only if you are confident it
  exists and is about them; otherwise "".
- `opponent_top_flight` — for a football match only: true if the opponent is a Premier League club; otherwise false.
