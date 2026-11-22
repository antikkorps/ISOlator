"""Build the extra initrd that lets a casper ISO boot from exFAT.

Everything comes from the ISO itself (its initrd scripts, its kernel's exfat
module), so the add-on always matches the kernel it is loaded with. Runs
unprivileged: the ISO is read in place, nothing is mounted.

Host tools, all Debian packages: unmkinitramfs (initramfs-tools-core),
unsquashfs (squashfs-tools), depmod (kmod).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from isolator.casper import (MODULES, changed_files, find_initrd_root, kernel_version,
                          patch_helpers, safe_path, snapshot)
from isolator.cpio import build_newc
from isolator.iso9660 import Iso

TOOLS = ("unmkinitramfs", "unsquashfs", "depmod")


class AddonError(Exception):
    pass


def _run(*cmd: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise AddonError(f"{cmd[0]} failed: {res.stderr.strip()[-500:]}")


def missing_tools() -> list[str]:
    return [t for t in TOOLS if shutil.which(t) is None]


def casper_file(iso: Iso, prefix: str) -> str:
    """casper/initrd, initrd.lz, initrd.gz... depending on the release."""
    names = sorted(n for n in iso.list_dir("casper") if n.lower().startswith(prefix))
    if not names:
        raise AddonError(f"no casper/{prefix}* in the ISO")
    return f"casper/{names[0]}"


def _squashfs_candidates(iso: Iso) -> list[str]:
    # filesystem (Mint, older Ubuntu) and minimal (Ubuntu 23.10+) hold the kernel modules.
    names = [n for n in iso.list_dir("casper") if n.endswith(".squashfs")]
    preferred = [n for n in ("filesystem.squashfs", "minimal.squashfs") if n in names]
    return [f"casper/{n}" for n in preferred]


def _extract_exfat(iso: Iso, version: str, dest: Path) -> Path:
    inner = f"{MODULES}/{version}/kernel/fs/exfat"
    errors = []
    for sq in _squashfs_candidates(iso):
        out = dest / sq.replace("/", "_")
        try:
            # A squashfs without the path may make unsquashfs fail: try the next one.
            _run("unsquashfs", "-q", "-n", "-o", str(iso.offset(sq)), "-d", str(out),
                 str(iso.path), inner)
            folder = safe_path(out, inner)
        except (AddonError, ValueError) as err:
            errors.append(f"{sq}: {err}")
            continue
        found = sorted(p for p in folder.glob("exfat.ko*") if p.is_file() and not p.is_symlink()) \
            if folder.is_dir() else []
        if found:
            return found[0]
    raise AddonError(f"exfat module for kernel {version} not found in the ISO {errors or ''}")


def _initrd_tree(iso: Iso, work: Path) -> Path:
    raw = work / "initrd.img"
    iso.extract(casper_file(iso, "initrd"), raw)
    _run("unmkinitramfs", str(raw), str(work / "unpacked"))
    return find_initrd_root(work / "unpacked")


def build_casper_addon(iso: Iso) -> bytes:
    """cpio archive to load after the ISO's own initrd."""
    with tempfile.TemporaryDirectory(prefix="isolator-") as tmp:
        work = Path(tmp)
        root = _initrd_tree(iso, work)
        version = kernel_version(root)
        mods = safe_path(root, f"{MODULES}/{version}")
        module = _extract_exfat(iso, version, work)
        before = snapshot(mods)
        target = safe_path(mods, f"kernel/fs/exfat/{module.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module, target, follow_symlinks=False)
        _run("depmod", "-b", str(root), version)
        helpers = patch_helpers(safe_path(root, "scripts/casper-helpers").read_text())
        files = {f"{MODULES}/{version}/{n}": ((mods / n).read_bytes(), 0o644)
                 for n in changed_files(mods, before)}
        files[f"{MODULES}/{version}/kernel/fs/exfat/{module.name}"] = (module.read_bytes(), 0o644)
        files["scripts/casper-helpers"] = (helpers.encode(), 0o755)
        return build_newc(files)
