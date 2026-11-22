"""Verify ISOs against the signed checksum files published by distributions.

Put the checksum file and its signature next to the ISO, as downloaded:
SHA256SUMS + SHA256SUMS.gpg (Ubuntu, Debian: .sign), sha256sum.txt + .gpg
(Mint), clearsigned *CHECKSUM (Fedora, Rocky), or x.iso.sig (CachyOS).
Only content covered by a valid signature from a pinned key is trusted.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from isolator.cache import DigestCache
from isolator.gpg import SignatureError, verify_clearsigned, verify_detached, verify_detached_file
from isolator.sums import parse_sums

SIG_EXTS = (".gpg", ".sig", ".sign", ".asc")
CLEARSIGN = b"-----BEGIN PGP SIGNED MESSAGE-----"
MAX_SUMS = 1 << 20


class Status(enum.Enum):
    VERIFIED = "verified"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "unverified"


@dataclass
class Report:
    iso: Path
    status: Status
    detail: str


@dataclass
class Keys:
    rings: list[Path]
    pinned: dict[str, str]  # fingerprint -> label


def load_pinned(path: Path) -> dict[str, str]:
    """trusted.txt: "<fingerprint>  <label>" per line, # for comments."""
    pinned = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            fpr, _, label = line.partition(" ")
            pinned[fpr.upper()] = label.strip()
    return pinned


def _signature_of(path: Path) -> Path | None:
    return next((s for ext in SIG_EXTS if (s := path.with_name(path.name + ext)).is_file()), None)


def _verified_text(path: Path, keys: Keys) -> tuple[str, bytes] | None:
    """(signer, signed content) of a checksum file, None if not signed."""
    data = path.read_bytes()
    pinned = set(keys.pinned)
    if data.lstrip().startswith(CLEARSIGN):
        return verify_clearsigned(data, keys.rings, pinned)
    sig = _signature_of(path)
    if sig is None:
        return None
    return verify_detached(data, sig.read_bytes(), keys.rings, pinned), data


def _is_iso(path: Path) -> bool:
    return path.suffix.lower() == ".iso"


def _candidates(directory: Path):
    """Regular files that may be checksum lists. Symlinks are skipped: on a
    disk the attacker controls they could point at anything on the host."""
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or _is_iso(path) or path.suffix in SIG_EXTS:
            continue
        if path.stat().st_size <= MAX_SUMS:
            yield path


def _merge(sums: dict, name: str, entry: tuple[str, str, str]) -> None:
    """Two signed lists disagreeing on a name (e.g. an old genuine list
    dropped next to the current one) verify nothing: None marks the conflict."""
    if name in sums and (sums[name] is None or sums[name][:2] != entry[:2]):
        sums[name] = None
    else:
        sums[name] = entry


def signed_sums(directory: Path, keys: Keys) -> tuple[dict[str, tuple[str, str, str] | None], list[str]]:
    """({iso name: (algo, digest, signer label) or None if conflicting}, warnings)."""
    sums: dict[str, tuple[str, str, str] | None] = {}
    warnings = []
    for path in _candidates(directory):
        try:
            verified = _verified_text(path, keys)
            if verified:
                signer, text = verified
                for name, (algo, digest) in parse_sums(text.decode("utf-8", "replace")).items():
                    _merge(sums, name, (algo, digest, keys.pinned[signer]))
        except (SignatureError, ValueError, OSError) as err:
            warnings.append(f"{path}: {err}")
    return sums, warnings


def _check_signed_iso(iso: Path, sig: Path, keys: Keys) -> Report:
    try:
        signer = verify_detached_file(iso, sig.read_bytes(), keys.rings, set(keys.pinned))
        return Report(iso, Status.VERIFIED, f"ISO signed by {keys.pinned[signer]}")
    except SignatureError as err:
        return Report(iso, Status.UNVERIFIED, f"{sig.name}: {err}")


def _check_listed(iso: Path, entry: tuple[str, str, str], cache: DigestCache) -> Report:
    algo, expected, label = entry
    digest, cached = cache.lookup(iso, algo)
    if digest != expected:
        return Report(iso, Status.MISMATCH, f"{algo} differs from the list signed by {label}")
    how = " (cached digest: path, size and mtime unchanged)" if cached else ""
    return Report(iso, Status.VERIFIED, f"{algo} matches the list signed by {label}{how}")


def check_iso(iso: Path, sums: dict, keys: Keys, cache: DigestCache) -> Report:
    if iso.is_symlink() or not iso.is_file():
        return Report(iso, Status.UNVERIFIED, "not a regular file (symlink or directory): not checked")
    try:
        sig = _signature_of(iso)
        if sig is not None:
            return _check_signed_iso(iso, sig, keys)
        if iso.name not in sums:
            return Report(iso, Status.UNVERIFIED, "not listed in any signed checksum file")
        if sums[iso.name] is None:
            return Report(iso, Status.UNVERIFIED, "conflicting signed checksum lists")
        return _check_listed(iso, sums[iso.name], cache)
    except OSError as err:
        return Report(iso, Status.UNVERIFIED, f"unreadable: {err}")


def find_isos(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory (disk not mounted?)")
    return sorted(root.rglob("*.iso", case_sensitive=False))


def verify_tree(root: Path, keys_dir: Path, warn=lambda msg: None,
                cache: DigestCache | None = None) -> list[Report]:
    cache = cache or DigestCache(None)
    keys = Keys(sorted(keys_dir.glob("*.gpg")), load_pinned(keys_dir / "trusted.txt"))
    isos, reports = find_isos(root), []
    for directory in sorted({p.parent for p in isos}):
        sums, warnings = signed_sums(directory, keys)
        for w in warnings:
            warn(w)
        reports += [check_iso(iso, sums, keys, cache) for iso in isos if iso.parent == directory]
    return reports
