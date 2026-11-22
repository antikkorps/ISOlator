# ISOlator

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-yellow?logo=buymeacoffee)](https://buymeacoffee.com/fvienot)

ISOlator is a hand-built multiboot USB disk: Debian's GRUB plus one exFAT partition for the
ISO files. A minimal, auditable alternative to Ventoy: no opaque binaries,
everything is a script you can read.

## Security by design

- **No third-party dependencies**: Python's standard library and tools packaged
  by Debian only. No pip, nothing downloaded besides the distribution.
- **ISOs are read in place**: built-in ISO9660 reader, no mount, no sudo.
- **Filtered input**: every ISO path, file name, label and kernel argument that
  reaches the GRUB script is whitelisted (`[A-Za-z0-9._+/-]`, plus `=:,` for
  kernel arguments); the menu is checked with `grub-script-check` before it is
  written, then written atomically.
- **Untrusted ISO content stays contained**: when building add-ons, symlinks
  and `..` from the ISO's initrd or squashfs are refused.
- **Signed checksums with pinned keys**: `verify-isos.py` trusts a checksum
  only if it is signed by a key whose fingerprint is pinned in
  `keys/trusted.txt` (see the sources in that file).
- **Destructive guard rails**: the installer checks the disk serial and bus,
  and refuses the system disk.

## Disk layout

| Partition | File system | Role |
|-----------|-------------|------|
| `MBOOT-EFI` (512 MB) | FAT32 | GRUB x86_64-efi in removable mode, minimal `grub.cfg` |
| `MULTIBOOT` (rest) | exFAT | ISOs, `multiboot/menu.cfg`, `multiboot/local.cfg`, `multiboot/addons/` |

## Usage

1. `sudo ./install-multiboot.sh /dev/sdX "<serial>"` (once; **erases the disk**).
   The serial is required and must match: get it with `lsblk -o NAME,SERIAL,TRAN,SIZE`.
2. Copy ISOs anywhere on `MULTIBOOT` (names without spaces or accents).
3. `./gen-menu.py` (or `--dry-run` to preview without writing).
4. Hand-written entries: `multiboot/local.cfg` on the disk (example in `examples/local.cfg`).
5. Optional, recommended: download each distribution's checksum file and its
   signature next to the ISO, then run `./verify-isos.py`.

## What `gen-menu.py` recognises

ISOs are identified by content, not by name:

| Family | Signature | Status |
|--------|-----------|--------|
| Anaconda (Rocky, Alma, RHEL…) | `.treeinfo` + `images/pxeboot/` | OK |
| Fedora Live | `LiveOS/squashfs.img` | OK |
| Ubuntu / Mint (casper) | `casper/vmlinuz` | OK, with an exFAT add-on (below) |
| loopback.cfg (Arch, CachyOS…) | `boot/grub/loopback.cfg` | OK |
| Debian installer | `install.amd/` | skipped: exFAT not supported yet |
| Debian Live | `live/vmlinuz` | skipped: exFAT not supported yet |
| Windows | `sources/install.wim` | skipped |
| ISO without `BOOTX64.EFI` (arm64) | — | skipped |

### The casper exFAT add-on

casper cannot read exFAT: its initrd has no exfat module, and its iso-scan only
tries a fixed list of file systems. For each casper ISO, `gen-menu.py` builds,
unprivileged and from the ISO itself, a small extra initrd
(`multiboot/addons/<name>-<hash>.img`) that GRUB loads after the ISO's own:

- the `exfat.ko` matching the initrd's kernel, taken from the ISO's squashfs;
- `modules.*` regenerated with `depmod`;
- the ISO's own `scripts/casper-helpers`, patched in two exact places (exfat
  added to the supported file systems and loaded with the others). An unknown
  casper version is refused rather than half-patched.

Host tools used: `unmkinitramfs` (initramfs-tools-core), `unsquashfs`
(squashfs-tools), `depmod` (kmod).

## Verifying ISOs

Put the files exactly as published next to the ISO; rename them freely if two
distributions use the same name (the signature covers the content, not the
name):

| Distribution | Files |
|--------------|-------|
| Ubuntu | `SHA256SUMS` + `SHA256SUMS.gpg` |
| Debian | `SHA512SUMS` + `SHA512SUMS.sign` |
| Linux Mint | `sha256sum.txt` + `sha256sum.txt.gpg` |
| Fedora | `*-CHECKSUM` (clearsigned) |
| Rocky | `<iso>.CHECKSUM` + `<iso>.CHECKSUM.asc` |
| CachyOS | `<iso>.sig` (signature of the ISO itself) |

`./verify-isos.py` exits with 0 if everything is verified, 1 if something is
unverified, and 2 on a checksum mismatch.

Digests are cached in `~/.cache/isolator/` (on the host, never on the disk) and
reused while an ISO keeps the same path, size and mtime; signatures are still
checked on every run. `--no-cache` re-reads everything.

## Development

```sh
python3 -m unittest discover -s tests -t .
```

Test ISOs are generated in Python at test time (`tests/isobuilder.py`).

## Roadmap

- [x] Disk installation
- [x] Automatic menu generation
- [x] Ubuntu / Mint from exFAT (casper add-on)
- [x] GPG verification of ISOs with pinned keys
- [ ] Debian installer / Debian Live from exFAT
- [ ] GRUB theme (icons through `--class`)
- [ ] Secure Boot with personal keys, GRUB arm64

## Support

ISOlator is a personal project. If it saves you a few USB sticks, you can
[buy me a coffee](https://buymeacoffee.com/fvienot).

## License

ISOlator is free software, released under the
[GNU General Public License v3.0](LICENSE): you may use, study, share and
modify it; modified versions you distribute must stay under the GPL-3.0.
