# The demo film

Ephe's own cutting tools — `film_card`, `film_music`, `film_sound`, `film_clip` and
`film_status` in `core/tools/film_tools.py`, joined by the cut in `core/film_cut.py` — were
built and shown by one 40 second film, assembled on 2026-11-19 from an HTML composition
that lives outside this repository. The film and its poster frame were retired from
`docs/media/` on 2026-11-24 by owner decision. The tree publishes no film; the only moving
picture that ships with the product is the first-run sequence under
`app/public/onboarding/`, which the product plays itself.

## What the film was made of

One brief in the composer produced five tool calls in one turn: `film_status`, `film_card`,
`film_card`, `film_music`, `film_clip`. Its title cards, its music bed and its spoken German
lines came out of those calls on one machine. The frames were Playwright captures of the
built PWA against a server started by `scripts/run_server.py`, each in a fresh browser
profile, because a profile holding a first-run state does not show the intro.

## What it did not claim

There is no text-to-video model in Ephe. The film showed a person answering the approval
gate in the chat, the tools writing real files, and the result playing back with its own
sound: a chain of local steps, each one open in this checkout. [`HISTORY.md`](HISTORY.md)
carries the same sentence in the record of why the tools were built.

## What this page used to hold

Two rows tabulated the mp4 and its poster with byte counts and checksums, and called the
mp4 the README's film block. No README names either file: measured across `README.md`,
`README.es.md` and `README.zh-CN.md` on 2026-11-24, the string appears in none of them, and
the block had left the README before the retirement did. The page also carried the path of
the render on the machine that made it. A checksum of a file the reader cannot open is not
a check, and a path on someone else's disk is not documentation, so both are gone. What
stays here is what a reader can still open in this checkout: the tools, the cut, and the
record of what one turn did.
