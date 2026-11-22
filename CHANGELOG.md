# Changelog

All notable changes to ISOlator are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/antikkorps/ISOlator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/antikkorps/ISOlator/releases/tag/v0.1.0
