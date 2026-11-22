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


def signed_sums(directory: Path, keys: Keys) -> tuple[dict[str, tuple[str, str, str]], list[str]]:
    """({iso name: (algo, digest, signer label)}, warnings) for one directory."""
    sums, warnings = {}, []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix in (".iso", *SIG_EXTS) or path.stat().st_size > MAX_SUMS:
            continue
        try:
            verified = _verified_text(path, keys)
            if verified:
                signer, text = verified
                for name, (algo, digest) in parse_sums(text.decode("utf-8", "replace")).items():
                    sums[name] = (algo, digest, keys.pinned[signer])
        except (SignatureError, ValueError) as err:
            warnings.append(f"{path}: {err}")
    return sums, warnings


def check_iso(iso: Path, sums: dict[str, tuple[str, str, str]], keys: Keys, cache: DigestCache) -> Report:
    sig = _signature_of(iso)
    if sig is not None:
        try:
            signer = verify_detached_file(iso, sig.read_bytes(), keys.rings, set(keys.pinned))
            return Report(iso, Status.VERIFIED, f"ISO signed by {keys.pinned[signer]}")
        except SignatureError as err:
            return Report(iso, Status.UNVERIFIED, f"{sig.name}: {err}")
    if iso.name not in sums:
        return Report(iso, Status.UNVERIFIED, "not listed in any signed checksum file")
    algo, expected, label = sums[iso.name]
    if cache.digest(iso, algo) != expected:
        return Report(iso, Status.MISMATCH, f"{algo} differs from the list signed by {label}")
    return Report(iso, Status.VERIFIED, f"{algo} matches the list signed by {label}")


def verify_tree(root: Path, keys_dir: Path, warn=lambda msg: None,
                cache: DigestCache | None = None) -> list[Report]:
    cache = cache or DigestCache(None)
    keys = Keys(sorted(keys_dir.glob("*.gpg")), load_pinned(keys_dir / "trusted.txt"))
    reports = []
    for directory in sorted({p.parent for p in root.rglob("*.iso")}):
        sums, warnings = signed_sums(directory, keys)
        for w in warnings:
            warn(w)
        reports += [check_iso(iso, sums, keys, cache) for iso in sorted(directory.glob("*.iso"))]
    return reports
