# Changelog

All notable changes to ISOlator are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Submenus in `isolator.toml`: `submenus = true` groups the entries as
  "Installers" and "Live systems" according to what each ISO is;
  `[[menu.submenu]]` blocks (`title`, `match` patterns) add custom submenus,
  which claim their entries first. The `default` entry still works inside a
  submenu. Submenu titles are whitelisted (`A-Z a-z 0-9 space . _ + ( ) -`,
  starting with a letter or digit so GRUB cannot read them as an option).

### Changed
- `set default` is now quoted in `menu.cfg`.

## [0.2.0] - 2026-11-23

### Security
- The whitelists for what reaches the GRUB script (paths, labels, kernel
  arguments, classes) ended with `$`, which in Python also accepts a trailing
  newline: an ISO with such a file name or label could add a line break to
  `menu.cfg`. They now end with `\Z`.

### Added
- Menu settings in `MULTIBOOT:/multiboot/isolator.toml` (sample in
  `examples/isolator.toml`): `timeout`, `default` entry, `order` and `hidden`
  patterns. The file is validated strictly: an unknown key or invalid value
  stops `gen-menu.py` with a message and leaves the current menu untouched.
- Each generated entry has a stable `--id` (its ISO path).
- `qemu-test.py`: boots the USB disk in a QEMU/OVMF virtual machine, with an
  optional qcow2 install target, to test a full installation or preview the
  menu without rebooting. Same serial/USB/system-disk guard rails as the
  installer; only the read-only `open()` of the device runs as root, QEMU runs
  as the user and receives the disk as a read-only descriptor. Guest RAM
  defaults to half the host's (at most 4 GB) so the host does not swap.

### Known limitations
- A full installation to disk has now been tested under QEMU/OVMF: Rocky
  Linux 9.9 installed from the ISOlator disk onto a virtual disk, then booted
  on its own to the GNOME first-boot screen. Not yet tested onto a physical
  disk, nor for Ubuntu, Mint, Fedora or CachyOS.
- `isolator.toml` (order, hidden entry, default entry, timeout) was checked on
  the real disk booted under `qemu-test.py`, not yet on a physical PC.

## [0.1.2] - 2026-11-22

### Known limitations
- Every supported family is now confirmed booting on real hardware (UEFI,
  USB disk): Ubuntu 26.04.1 and Linux Mint 22.3 through the casper exFAT
  add-on, Fedora Live, Rocky (Anaconda installer starts) and CachyOS
  (loopback.cfg). The 0.1.0 limitation "not yet booted on real hardware" no
  longer applies. A full installation to disk has not been tested yet.

## [0.1.1] - 2026-11-22

### Security
- Signatures made by a revoked or expired key, and expired signatures, are
  now refused (previously only bad signatures were); a revoked key anywhere in
  a file refuses the whole file.
- Two signed checksum lists disagreeing about the same ISO now verify nothing
  instead of the last one silently winning (downgrade with an old genuine list).
- The digest cache is now opt-in (`--cache`) and cached results are flagged:
  size and mtime can be forged by whoever had the disk.
- Symlinks and non-regular files are never reported as verified, and are not
  read as checksum lists.

### Fixed
- `verify-isos.py` exited 0 when the disk was not mounted or held no ISO.
- ISOs with an uppercase `.ISO` extension were ignored by `verify-isos.py` and
  `gen-menu.py`.
- An unreadable file no longer aborts the whole verification.

### Added
- Release process documented in `CLAUDE.md`; roadmap extended (full GRUB
  customisation, graphical front-end).

## [0.1.0] - 2026-11-22

First public release.

### Added
- `install-multiboot.sh`: turns a USB disk into a GPT disk with a FAT32 ESP
  (Debian's GRUB, removable mode, NVRAM untouched) and an exFAT partition for
  ISOs. Requires the device and its serial as arguments; refuses non-USB disks
  and the running system's disk.
- `gen-menu.py`: identifies each ISO by its content with a built-in read-only
  ISO9660 reader (no mount, no sudo) and writes the GRUB menu, validated with
  `grub-script-check` and written atomically. Supported: Anaconda installers
  (Rocky, Alma, RHEL…), Fedora Live, loopback.cfg ISOs (Arch, CachyOS…).
- Ubuntu / Linux Mint (casper) boot from exFAT through a small extra initrd
  generated, unprivileged, from the ISO itself (its kernel's `exfat.ko`,
  `depmod` metadata, and its own `casper-helpers` patched in two exact places).
- `verify-isos.py`: verifies ISOs against the distributions' signed checksum
  files with `gpgv`, accepting only keys whose fingerprints are pinned in
  `keys/trusted.txt` (Ubuntu, Debian, Fedora 45, Rocky 9/10, Linux Mint,
  CachyOS), with a host-side digest cache.
- Test suite (`python3 -m unittest discover -s tests -t .`) with ISO images
  generated at test time.

### Security
- Everything derived from ISO content (paths, Rock Ridge names, labels, kernel
  arguments, `.treeinfo` values) is whitelisted before reaching GRUB.
- Symlinks and `..` from an ISO's initrd or squashfs are refused when building
  the casper add-on.

### Known limitations
- The casper exFAT add-on is validated on Ubuntu 26.04.1 and Linux Mint 22.3
  images and their initrds, but not yet booted on real hardware.
- Debian installer / Debian Live, Windows and arm64 ISOs are not bootable yet.

[Unreleased]: https://github.com/antikkorps/ISOlator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/antikkorps/ISOlator/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/antikkorps/ISOlator/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/antikkorps/ISOlator/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/antikkorps/ISOlator/releases/tag/v0.1.0
