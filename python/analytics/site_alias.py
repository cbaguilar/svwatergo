from __future__ import annotations


SITE_TITLE_ALIASES = (
    ("Bluerock", "Site A"),
    ("Santa Teresa", "Site B"),
    ("Pryor Farm", "Site C"),
    ("Pryorfarm", "Site C"),
    ("santateresa", "site B"),
    ("pryorfarm", "site C"),
    ("bluerock", "site A"),
)


def alias_site_names(text: str) -> str:
    out = str(text)
    for src, dst in SITE_TITLE_ALIASES:
        out = out.replace(src, dst)
    return out
