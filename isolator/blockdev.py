"""Identify a block device and decide whether ISOlator may touch it.

Same guard rails as install-multiboot.sh: the caller must name the disk's
serial, because sda/sdb can be renumbered and two disks of the same model
often have near-identical serials.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskInfo:
    name: str
    serial: str
    tran: str
    holds_root: bool
    rdev: tuple[int, int]


def check_disk(info: DiskInfo, expected_serial: str) -> str | None:
    """Return why the disk must not be used, or None if it is acceptable."""
    if not expected_serial or info.serial != expected_serial:
        return f"{info.name} has serial '{info.serial}', expected '{expected_serial}'"
    if info.tran != "usb":
        return f"{info.name} is not a USB disk ({info.tran or 'unknown bus'})"
    if info.holds_root:
        return f"{info.name} holds the running system"
    return None


def _run(*argv: str) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout


def root_names(raw: str) -> set[str]:
    """Names from `lsblk -nrso NAME`: raw mode, no tree-drawing prefixes."""
    return set(raw.split())


def _root_disks() -> set[str]:
    # --nofsroot: btrfs subvolumes otherwise come out as /dev/sda2[/@].
    source = _run("findmnt", "-nvo", "SOURCE", "/").strip()
    return root_names(_run("lsblk", "-nrso", "NAME", source))


def parse_disk(lsblk_json: str, root: set[str]) -> DiskInfo:
    dev = json.loads(lsblk_json)["blockdevices"][0]
    major, minor = dev["maj:min"].split(":")
    return DiskInfo(name=dev["name"], serial=(dev.get("serial") or "").strip(),
                    tran=dev.get("tran") or "", holds_root=dev["name"] in root,
                    rdev=(int(major), int(minor)))


def read_disk(device: Path) -> DiskInfo:
    out = _run("lsblk", "-J", "-d", "-o", "NAME,SERIAL,TRAN,MAJ:MIN", str(device))
    return parse_disk(out, _root_disks())
