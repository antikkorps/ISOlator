"""Checksum files as distributions publish them, and file hashing."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# GNU coreutils: "<hex>  name" or "<hex> *name"; BSD/Fedora/Rocky: "SHA256 (name) = <hex>".
_GNU = re.compile(r"^([0-9a-fA-F]+) [ *](\S+)$")
_BSD = re.compile(r"^(SHA256|SHA512) \((\S+)\) = ([0-9a-fA-F]+)$")
_BY_LENGTH = {64: "sha256", 128: "sha512"}


def _parse_line(line: str) -> tuple[str, str, str] | None:
    if m := _BSD.match(line):
        algo, name, digest = m.group(1).lower(), m.group(2), m.group(3)
    elif m := _GNU.match(line):
        digest, name = m.group(1), m.group(2)
        algo = _BY_LENGTH.get(len(digest), "")
    else:
        return None
    if not algo or len(digest) != hashlib.new(algo).digest_size * 2:
        return None
    # Entries for other directories are ignored: we only match by base name,
    # and "./x.iso" is the common way of listing a file of the same directory.
    name = name.removeprefix("./")
    return (name, algo, digest.lower()) if "/" not in name else None


def parse_sums(text: str) -> dict[str, tuple[str, str]]:
    """{file name: (algorithm, lowercase hex digest)}."""
    sums: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        parsed = _parse_line(line.strip())
        if parsed is None:
            continue
        name, algo, digest = parsed
        if sums.get(name, (algo, digest)) != (algo, digest):
            raise ValueError(f"conflicting checksums for {name}")
        sums[name] = (algo, digest)
    return sums


def file_digest(path: Path, algo: str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, algo).hexdigest()
