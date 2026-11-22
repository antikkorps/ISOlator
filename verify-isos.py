#!/usr/bin/env python3
"""verify-isos.py - check every ISO against its distribution's signed checksums.

Download the checksum file and its signature next to each ISO (see
isolator/verify.py for the names). Signatures are checked with gpgv against
keys/*.gpg, and only keys whose fingerprint is pinned in keys/trusted.txt
are accepted. Read-only: nothing on the disk is modified.

--cache reuses digests from ~/.cache/isolator for ISOs whose path, size and
mtime are unchanged. Those can be forged by whoever had the disk, so cached
results are flagged and the default re-reads every ISO.

Usage:
    ./verify-isos.py [--root /media/$USER/MULTIBOOT] [--cache]
Exit status: 0 all verified, 1 something unverified, 2 a checksum MISMATCH.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from isolator.cache import DigestCache, default_store
from isolator.verify import Status, verify_tree

KEYS = Path(__file__).resolve().parent / "keys"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(f"/media/{getpass.getuser()}/MULTIBOOT"),
                    help="mount point of the MULTIBOOT partition")
    ap.add_argument("--keys", type=Path, default=KEYS, help="directory with *.gpg and trusted.txt")
    ap.add_argument("--cache", action="store_true",
                    help="reuse digests of ISOs with unchanged path, size and mtime (faster, weaker)")
    args = ap.parse_args()

    cache = DigestCache(default_store() if args.cache else None)
    try:
        reports = verify_tree(args.root, args.keys, cache=cache,
                              warn=lambda m: print(f"  warning  {m}", file=sys.stderr))
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    cache.save()
    if not reports:
        print(f"error: no ISO found under {args.root}", file=sys.stderr)
        return 1
    for r in reports:
        print(f"  {r.status.value:<10} {r.iso.relative_to(args.root)}\n             {r.detail}")
    statuses = {r.status for r in reports}
    if Status.MISMATCH in statuses:
        print("\nAt least one ISO does NOT match its signed checksum: do not boot it.", file=sys.stderr)
        return 2
    return 1 if Status.UNVERIFIED in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
