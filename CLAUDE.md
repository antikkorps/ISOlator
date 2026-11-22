# CLAUDE.md

## Project

ISOlator (repo: isolator-boot; Python package `isolator/`): a hand-built
multiboot USB disk. Debian's GRUB (x86_64-efi,
removable mode) on a small FAT32 ESP, plus one exFAT partition holding the ISO
files. A minimal, auditable alternative to Ventoy: no opaque binaries,
everything is a script you can read. Intended to be published as open source.

Overview, disk layout and supported ISO families: @README.md

- Language: Python 3 (standard library only) and Bash.
- Target: Debian 13 host; built with the Debian packages `grub-efi-amd64-bin`,
  `grub-common`, `parted`, `dosfstools`, `exfatprogs`; menu generation also
  uses `initramfs-tools-core` (unmkinitramfs), `squashfs-tools`, `kmod`.

## Commands

- Generate the menu (preview, writes nothing): `./gen-menu.py --dry-run`
- Generate the menu onto the disk: `./gen-menu.py [--root /media/$USER/MULTIBOOT]`
- Prepare the disk (ERASES IT, root): `sudo ./install-multiboot.sh /dev/sdX "<serial>"`
- Tests: `python3 -m unittest discover -s tests -t .`
- Shell lint: `shellcheck install-multiboot.sh`
- GRUB syntax: `grub-script-check examples/local.cfg`

## Before pushing

```sh
python3 -m unittest discover -s tests -t . && bash -n install-multiboot.sh && shellcheck install-multiboot.sh && grub-script-check examples/local.cfg
```

## Workflow

- Plan first, then TDD: write the failing test and show the RED output before
  implementing; re-run and show the GREEN output after.
- One function, one responsibility. Functions under 30 lines, files under ~200
  lines; split by responsibility, never arbitrarily.
- DRY with judgement: factor out on the third repetition; no abstraction with a
  single caller. Flag DRY violations.
- Use current best practices for the versions already installed. No deprecated
  APIs. Never add a dependency without saying so and why.
- Comments in English, explaining why, not what.
- At the end of each feature, delegate a code review to a subagent that
  receives only the diff and the spec.
- Before every push: run the "Before pushing" command from the repo's
  CLAUDE.md; do not push if it fails; never use `--no-verify`; paste the test
  output in the summary.

## Code structure

- `isolator/`: the library (ISO9660 reader, profiles, menu, casper exFAT
  add-on, cpio writer, GPG/checksum verification); scripts are thin CLIs.
- `gen-menu.py`: reads each ISO with a built-in read-only ISO9660 reader
  (no mount, no sudo), identifies it by content via "profiles" (one per
  distro family, ordered from most specific to most generic), writes
  `MULTIBOOT:/multiboot/menu.cfg` after validating it with `grub-script-check`.
- `install-multiboot.sh`: partitions, formats and installs GRUB on the target
  disk. Destructive.
- `examples/local.cfg`: sample of hand-written entries (chainload of the
  internal OS). On the disk, `multiboot/local.cfg` is never overwritten.
- `verify-isos.py` + `keys/`: ISO verification; `keys/trusted.txt` pins the
  accepted fingerprints, each with its official source. Never add a key
  without its source page and a fingerprint check.
- `tests/`: unittest suite; test ISOs are built in Python at test time,
  never committed.

## Project-specific rules

- Zero runtime dependencies: only Python's standard library and tools shipped
  by Debian. No pip, no vendored or downloaded binaries. `shellcheck` is a
  dev-only tool.
- Security by design: anything that ends up in a GRUB script must pass the
  `SAFE_PATH` whitelist (`[A-Za-z0-9._+/-]`, see `isolator/profiles.py`); never interpolate unfiltered
  ISO metadata or file names into `menu.cfg`.
- Everything the boot path relies on must stay read-only towards the disk
  (loop/dm mappings read-only, ISO files never modified).
- Never run `install-multiboot.sh`, `grub-install`, `parted`, `mkfs.*`,
  `wipefs`, `dd` or any write to a block device without the user's explicit
  approval for that specific command. Always check the disk serial first:
  two disks of the same model can be plugged at once.
- Commands needing root are run by the user in their own terminal; give them
  the exact command instead of running sudo.
- Language: code, comments, CLI messages and docs are in English (migration
  from French in progress; translate what you touch).
- Never put personal data (disk serials, filesystem UUIDs, user names) in
  committed code or examples: use placeholders (`XXXX-XXXX`) or arguments.
- No `Co-Authored-By` or other Claude attribution in commits.
- License: GPL-3.0 (`LICENSE`); new files fall under it.
