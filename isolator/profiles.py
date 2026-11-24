"""Boot profiles: recognise an ISO by its content and write its GRUB entry.

Each profile returns None when the ISO is not of its family, otherwise a
Result, possibly with a refusal (recognised but not bootable from exFAT).
"""
from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from isolator.addon import AddonError, build_casper_addon, casper_file, missing_tools
from isolator.casper import PatchError
from isolator.iso9660 import Iso

# Anything reaching a GRUB script is restricted to these characters: no
# space, quote, $, ; or backtick, so ISO content cannot inject commands.
# \Z, not $: "$" also matches before a trailing newline.
SAFE_PATH = re.compile(r"^[A-Za-z0-9._+/-]+\Z")
SAFE_ARG = re.compile(r"^[A-Za-z0-9._+/=:,-]+\Z")
SAFE_CLASS = re.compile(r"^[a-z0-9_-]+\Z")
ISO_SCAN = "iso-scan/filename=$iso"


@dataclass
class Result:
    title: str = ""
    css_class: str = ""
    body: str = ""            # GRUB lines inside the menuentry, after loopback
    refusal: str = ""         # non-empty: recognised but not bootable
    addon: bytes | None = None  # extra initrd, referenced as $addon in body
    category: str = "live"    # "install" or "live": picks the automatic submenu


def readable_name(filename: str) -> str:
    """"Fedora-Workstation-Live-45-1.4.x86_64.iso" -> "Fedora Workstation Live 45 1.4"."""
    s = re.sub(r"\.iso$", "", filename, flags=re.I)
    s = re.sub(r"[._-]?(x86_64|amd64|64bit|x64)\b", "", s, flags=re.I)
    s = re.sub(r"[-_]+", " ", s).strip()
    return s[:1].upper() + s[1:]


def grub_path(iso: Iso, path: str) -> str:
    """Name of a file of the ISO as recorded in it, checked before it goes
    into a GRUB script: Rock Ridge names may contain newlines or quotes."""
    name = iso.real_name(path)
    if not SAFE_PATH.match(name):
        raise ValueError(f"unsafe file name in the ISO: {name!r}")
    return name


def anaconda(iso: Iso, rel: str, **_) -> Result | None:
    """Anaconda installers: Rocky, Alma, RHEL, CentOS Stream, Fedora Server."""
    if not (iso.has(".treeinfo") and iso.has("images/pxeboot/vmlinuz")):
        return None
    ti = configparser.ConfigParser(interpolation=None, strict=False)
    ti.read_string(iso.read(".treeinfo"))
    name = (ti.get("release", "name", fallback="") + " " + ti.get("release", "version", fallback="")).strip() \
        or ti.get("general", "name", fallback="") or readable_name(Path(rel).name)
    family = (ti.get("release", "short", fallback="") or ti.get("general", "family", fallback="")).lower().split()
    css = family[0] if family and SAFE_CLASS.match(family[0]) else "redhat"
    try:
        k, i = grub_path(iso, "images/pxeboot/vmlinuz"), grub_path(iso, "images/pxeboot/initrd.img")
    except (ValueError, FileNotFoundError) as err:
        return Result(refusal=f"anaconda: {err}")
    return Result(
        title=f"{name} - install", css_class=css, category="install",
        body=(f"    linux  (loop)/{k} inst.stage2=hd:LABEL=$isolabel:$iso inst.repo=hd:LABEL=$isolabel:$iso quiet\n"
              f"    initrd (loop)/{i}\n"))


def fedora_live(iso: Iso, rel: str, **_) -> Result | None:
    """Fedora Live (dracut dmsquash-live); two layouts depending on the release."""
    if not iso.has("LiveOS/squashfs.img"):
        return None
    for k, i in (("boot/x86_64/loader/linux", "boot/x86_64/loader/initrd"),
                 ("images/pxeboot/vmlinuz", "images/pxeboot/initrd.img")):
        if iso.has(k) and iso.has(i):
            break
    else:
        return Result(refusal="dracut live image but no kernel found")
    label = iso.label()
    if not SAFE_PATH.match(label):
        return Result(refusal=f"unexpected volume label: {label!r}")
    try:
        k, i = grub_path(iso, k), grub_path(iso, i)
    except ValueError as err:
        return Result(refusal=f"dracut live: {err}")
    return Result(
        title=f"{readable_name(Path(rel).name)} - live", css_class="fedora",
        body=(f"    linux  (loop)/{k} root=live:CDLABEL={label} rd.live.image iso-scan/filename=$iso quiet rhgb\n"
              f"    initrd (loop)/{i}\n"))


def casper_args(cfg: str) -> str:
    """Kernel arguments of the first `linux` line of the ISO's own menu."""
    m = re.search(r"^\s*linux\s+\S+(.*)$", cfg, re.M)
    if not m:
        raise ValueError("no linux line in the ISO's GRUB menu")
    args = [ISO_SCAN if a == "iso-scan/filename=${iso_path}" else a for a in m.group(1).split()]
    for a in args:
        if a != ISO_SCAN and not SAFE_ARG.match(a):
            raise ValueError(f"unsafe kernel argument in the ISO's menu: {a!r}")
    if ISO_SCAN not in args:
        args.insert(0, ISO_SCAN)
    return " ".join(args)


def _casper_menu(iso: Iso) -> str:
    cfg = iso.read("boot/grub/loopback.cfg") if iso.has("boot/grub/loopback.cfg") else ""
    if not re.search(r"^\s*linux\s", cfg, re.M) and iso.has("boot/grub/grub.cfg"):
        cfg = iso.read("boot/grub/grub.cfg")
    return cfg


def casper(iso: Iso, rel: str, build_addon: Callable[[Iso], bytes] = build_casper_addon, **_) -> Result | None:
    """Ubuntu, Mint and derivatives: booted with an extra initrd adding exFAT."""
    if not iso.has("casper/vmlinuz"):
        return None
    if build_addon is build_casper_addon and missing_tools():
        return Result(refusal=f"missing host tools: {', '.join(missing_tools())}")
    try:
        args = casper_args(_casper_menu(iso))
        kernel = grub_path(iso, "casper/vmlinuz")
        initrd = grub_path(iso, casper_file(iso, "initrd"))
        addon = build_addon(iso)
    except (ValueError, FileNotFoundError, AddonError, PatchError) as err:
        return Result(refusal=f"casper: {err}")
    return Result(
        title=f"{readable_name(Path(rel).name)} - live", css_class="ubuntu",
        body=(f"    linux  (loop)/{kernel} {args}\n"
              f"    initrd (loop)/{initrd} $addon\n"),
        addon=addon)


def _refuse(signature: tuple[str, ...], reason: str):
    def profile(iso: Iso, rel: str, **_) -> Result | None:
        return Result(refusal=reason) if any(iso.has(s) for s in signature) else None
    return profile


def loopback(iso: Iso, rel: str, **_) -> Result | None:
    """loopback.cfg convention (Arch, CachyOS, Manjaro, Kali...): the ISO
    brings its own menu. Last, since casper ISOs also ship one."""
    if not iso.has("boot/grub/loopback.cfg"):
        return None
    try:
        cfg = grub_path(iso, "boot/grub/loopback.cfg")
    except ValueError as err:
        return Result(refusal=f"loopback.cfg: {err}")
    return Result(
        title=f"{readable_name(Path(rel).name)} - live (ISO menu)",
        css_class="arch" if iso.has("arch/boot/x86_64") else "linux",
        body=("    set iso_path=$iso\n    export iso_path\n    set root=(loop)\n"
              f"    configfile /{cfg}\n"))


# Order matters: most specific first.
PROFILES = [
    anaconda, fedora_live, casper,
    _refuse(("install.amd/vmlinuz",), "debian-installer: exFAT not supported yet"),
    _refuse(("live/vmlinuz",), "live-boot: exFAT not supported yet"),
    _refuse(("sources/install.wim", "sources/install.esd"), "Windows: not bootable through GRUB loopback"),
    loopback,
]


def detect(iso: Iso, rel: str, **options) -> Result | None:
    for profile in PROFILES:
        result = profile(iso, rel, **options)
        if result is not None:
            return result
    return None
