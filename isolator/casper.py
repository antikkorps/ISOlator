"""Teach casper (Ubuntu, Mint) to find its ISO on an exFAT partition.

casper's iso-scan only mounts file systems listed in is_supported_fs, and the
initrd ships no exfat module. The fix keeps the distro's own scripts: the
ISO's casper-helpers is patched in two exact places, and must match exactly
once each, so an unknown casper version is refused rather than half-patched.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

MODULES = "usr/lib/modules"
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class PatchError(Exception):
    pass


_PATCHES = (
    # (pattern, replacement, what it does)
    (re.compile(r"^(\s+)(ext2\|ext3\|ext4\|[^)\n]*\))", re.M), r"\1exfat|\2",
     "declare exfat in is_supported_fs"),
    (re.compile(r"^(\s+)modprobe ext4\n", re.M), r"\1modprobe ext4\n\1modprobe exfat\n",
     "load the exfat module in wait_for_devs"),
)


def patch_helpers(text: str) -> str:
    for pattern, replacement, purpose in _PATCHES:
        text, count = pattern.subn(replacement, text)
        if count != 1:
            raise PatchError(f"casper-helpers: cannot {purpose} ({count} matches, expected 1)")
    return text


# ------------------------------------------------------------- initrd pieces
def safe_path(base: Path, rel: str) -> Path:
    """`base/rel`, refusing symlinks and `..` on the way. The unpacked
    initrd and squashfs come from the ISO: a planted symlink must not make
    us read host files (into the add-on) or write outside the temp dir."""
    path = base
    for part in Path(rel).parts:
        if part in ("..", "/"):
            raise ValueError(f"unsafe path in the ISO: {rel!r}")
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink in the ISO where a real file is expected: {rel!r}")
    return path


def find_initrd_root(unpacked: Path) -> Path:
    """unmkinitramfs puts each concatenated archive in its own directory
    (early/, main/...) or everything at the top when there is only one."""
    for candidate in [unpacked, *sorted(p for p in unpacked.iterdir() if p.is_dir())]:
        if (candidate / "scripts/casper-helpers").is_file():
            return candidate
    raise FileNotFoundError("scripts/casper-helpers not found in the initrd")


def kernel_version(root: Path) -> str:
    modules = safe_path(root, MODULES)
    if not modules.is_dir():
        raise ValueError(f"no {MODULES} in the initrd")
    versions = [p.name for p in modules.iterdir() if p.is_dir() or p.is_symlink()]
    if len(versions) != 1:
        raise ValueError(f"expected one kernel in the initrd, found {versions}")
    # The name is passed to depmod: no leading "-" that would read as an option.
    if not SAFE_VERSION.match(versions[0]) or (modules / versions[0]).is_symlink():
        raise ValueError(f"unexpected kernel directory {versions[0]!r}")
    return versions[0]


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: hashlib.sha256(p.read_bytes()).digest()
            for p in directory.iterdir() if p.is_file() and not p.is_symlink()}


def changed_files(directory: Path, before: dict[str, bytes]) -> list[str]:
    after = snapshot(directory)
    return sorted(name for name, digest in after.items() if before.get(name) != digest)
