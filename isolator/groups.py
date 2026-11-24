"""Split the arranged menu entries into top-level entries and GRUB submenus."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from isolator.config import MenuConfig
from isolator.profiles import Result

Entries = list[tuple[str, Result]]

# Automatic submenus, by profile category, in menu order.
CATEGORIES = (("install", "isolator-install", "Installers"),
              ("live", "isolator-live", "Live systems"))


@dataclass(frozen=True)
class Group:
    id: str          # GRUB --id; also the prefix of its entries' default id
    title: str       # SAFE_TITLE, checked by the config parser
    entries: Entries


def matches(rel: str, pattern: str) -> bool:
    # exFAT ignores case, so patterns do too.
    return fnmatch.fnmatchcase(rel.lower(), pattern.lower())


def _take(rest: Entries, wanted) -> tuple[Entries, Entries]:
    """(entries for which wanted() is true, the others), both in order."""
    return [e for e in rest if wanted(e)], [e for e in rest if not wanted(e)]


def group(shown: Entries, cfg: MenuConfig) -> tuple[Entries, list[Group]]:
    """Custom submenus claim their entries first (the first match wins), then
    `submenus = true` sorts what is left by category. Empty groups are dropped."""
    custom, rest = [], shown
    for n, sub in enumerate(cfg.submenu, 1):
        members, rest = _take(rest, lambda e, s=sub: any(matches(e[0], p) for p in s.match))
        custom.append(Group(f"isolator-submenu-{n}", sub.title, members))
    auto = []
    if cfg.submenus:
        for category, gid, title in CATEGORIES:
            members, rest = _take(rest, lambda e, c=category: e[1].category == c)
            auto.append(Group(gid, title, members))
    return rest, [g for g in auto + custom if g.entries]


def entry_ids(top: Entries, groups: list[Group]) -> dict[str, str]:
    """ISO path -> the id `set default` needs: "submenu>entry" inside a submenu."""
    ids = {rel: rel for rel, _ in top}
    for g in groups:
        ids.update({rel: f"{g.id}>{rel}" for rel, _ in g.entries})
    return ids
