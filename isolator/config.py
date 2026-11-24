"""User configuration of the menu: MULTIBOOT:/multiboot/isolator.toml.

The file lives on the disk, so it is untrusted input like the ISOs: unknown
keys are refused (a typo must not be silently ignored) and anything that
reaches the GRUB script passes the same whitelist as the ISO paths.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from isolator.profiles import SAFE_PATH

MAX_TIMEOUT = 3600
# Submenu titles go between double quotes in menu.cfg: no " $ \\ { } or newline.
# GRUB strips the quotes before parsing options, so a leading "-" would be
# read as an option of `submenu`: the title must start with a letter or digit.
SAFE_TITLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,59}\Z")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Submenu:
    title: str
    match: tuple[str, ...]          # glob patterns, as in `order`


@dataclass(frozen=True)
class MenuConfig:
    timeout: int | None = None      # seconds; -1 waits forever
    default: str | None = None      # ISO path, also the entry's --id
    order: tuple[str, ...] = ()     # glob patterns, listed first in this order
    hidden: tuple[str, ...] = ()    # glob patterns left out of the menu
    submenus: bool = False          # group the rest as Installers / Live systems
    submenu: tuple[Submenu, ...] = ()


def _timeout(value: object) -> int:
    # bool is an int in Python: `timeout = true` must not mean 1 second.
    if type(value) is not int or not -1 <= value <= MAX_TIMEOUT:
        raise ConfigError(f"menu.timeout must be an integer from -1 to {MAX_TIMEOUT}")
    return value


def _default(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("/") or not SAFE_PATH.match(value):
        raise ConfigError("menu.default must be an ISO path such as \"/x86_64/name.iso\" "
                          "(characters A-Z a-z 0-9 . _ + / - only)")
    return value


def _patterns(key: str, value: object) -> tuple[str, ...]:
    # A pattern without the leading "/" would silently match nothing.
    if not isinstance(value, list) or not all(isinstance(v, str) and v.startswith("/")
                                              for v in value):
        raise ConfigError(f"menu.{key} must be a list of paths starting with \"/\", "
                          f"e.g. [\"/x86_64/ubuntu-*\"]")
    return tuple(value)


def _submenus(value: object) -> bool:
    if type(value) is not bool:
        raise ConfigError("menu.submenus must be true or false")
    return value


def _refuse_unknown(table: dict, known: set[str], where: str) -> None:
    unknown = set(table) - known
    if unknown:
        raise ConfigError(f"unknown key(s) in {where}: {', '.join(sorted(unknown))}")


def _submenu(table: object) -> Submenu:
    if not isinstance(table, dict):
        raise ConfigError("menu.submenu must be written as [[menu.submenu]] blocks")
    _refuse_unknown(table, {"title", "match"}, "[[menu.submenu]]")
    title = table.get("title")
    if not isinstance(title, str) or not SAFE_TITLE.match(title):
        raise ConfigError("menu.submenu.title must be 1 to 60 characters among "
                          "A-Z a-z 0-9 space . _ + ( ) -, starting with a letter or digit")
    if "match" not in table:
        raise ConfigError(f"[[menu.submenu]] \"{title}\" needs a match list")
    match = _patterns("submenu.match", table["match"])
    if not match:
        raise ConfigError(f"[[menu.submenu]] \"{title}\": match must not be empty")
    return Submenu(title, match)


def _menu(table: dict) -> MenuConfig:
    _refuse_unknown(table, {"timeout", "default", "order", "hidden", "submenus", "submenu"},
                    "[menu]")
    subs = table.get("submenu", [])
    if not isinstance(subs, list):
        raise ConfigError("menu.submenu must be written as [[menu.submenu]] blocks")
    return MenuConfig(
        timeout=_timeout(table["timeout"]) if "timeout" in table else None,
        default=_default(table["default"]) if "default" in table else None,
        order=_patterns("order", table.get("order", [])),
        hidden=_patterns("hidden", table.get("hidden", [])),
        submenus=_submenus(table.get("submenus", False)),
        submenu=tuple(_submenu(t) for t in subs))


def parse_config(text: str) -> MenuConfig:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"invalid TOML: {err}") from None
    unknown = set(data) - {"menu"}
    if unknown:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
    menu = data.get("menu", {})
    if not isinstance(menu, dict):
        raise ConfigError("[menu] must be a table")
    return _menu(menu)


def load_config(path: Path) -> MenuConfig:
    """MenuConfig() when the file does not exist: the config is optional."""
    try:
        return parse_config(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return MenuConfig()
    except (ConfigError, OSError, UnicodeDecodeError) as err:
        raise ConfigError(f"{path}: {err}") from None
