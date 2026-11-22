#!/usr/bin/env python3
"""gen-menu.py - generate the GRUB menu of the multiboot disk from its ISOs.

Each ISO is read in place (built-in ISO9660 reader: no mount, no sudo) and
recognised by its content. Casper ISOs (Ubuntu, Mint) also get an extra
initrd in multiboot/addons/ that adds exFAT support.

Usage:
    ./gen-menu.py                    # writes /media/$USER/MULTIBOOT/multiboot/menu.cfg
    ./gen-menu.py --root /path/to/MULTIBOOT
    ./gen-menu.py --dry-run          # print the menu, write nothing

Hand-written entries go in multiboot/local.cfg on the disk.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from isolator.menu import analyse, check_syntax, render, write


def report(kept, skipped) -> None:
    for rel, r in kept:
        extra = " (+exFAT add-on)" if r.addon is not None else ""
        print(f"  OK       {r.title:<45} {rel}{extra}", file=sys.stderr)
    for rel, reason in skipped:
        print(f"  skipped  {rel}\n           -> {reason}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(f"/media/{getpass.getuser()}/MULTIBOOT"),
                    help="mount point of the MULTIBOOT partition")
    ap.add_argument("--dry-run", action="store_true", help="print the menu without writing it")
    args = ap.parse_args()
    if not (args.root / "multiboot").is_dir():
        sys.exit(f"{args.root}/multiboot not found: is the MULTIBOOT partition mounted?")

    kept, skipped = analyse(args.root)
    menu = render(kept)
    errors = check_syntax(menu)
    if errors:
        print(menu)
        sys.exit(f"grub-script-check rejected the menu:\n{errors}")
    report(kept, skipped)
    if args.dry_run:
        print(menu)
        return 0
    target = write(args.root, kept)
    print(f"\n{target} written ({len(kept)} entries, previous menu in menu.cfg.bak)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
