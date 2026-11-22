"""Writer for the cpio "newc" format, the one the Linux kernel unpacks as an
initramfs. GRUB can load several initrds; the kernel unpacks them in order,
so a small archive appended after the distro's own initrd overrides or adds
files without rebuilding the original."""
from __future__ import annotations

from pathlib import PurePosixPath

S_IFDIR, S_IFREG = 0o040000, 0o100000


def _check(name: str) -> None:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe path in cpio archive: {name!r}")


def _pad4(n: int) -> bytes:
    return b"\0" * (-n % 4)


def _entry(ino: int, name: str, mode: int, data: bytes = b"") -> bytes:
    raw = name.encode() + b"\0"
    fields = (ino, mode, 0, 0, 1 if mode & S_IFREG else 2, 0, len(data),
              0, 0, 0, 0, len(raw), 0)
    header = b"070701" + b"".join(b"%08X" % f for f in fields)
    return header + raw + _pad4(len(header) + len(raw)) + data + _pad4(len(data))


def _parents(names) -> list[str]:
    dirs = set()
    for name in names:
        dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    return sorted(dirs)


def build_newc(files: dict[str, tuple[bytes, int]]) -> bytes:
    """Archive {path: (content, permission bits)}; parent directories are
    added so the kernel can create files in directories it lacks."""
    for name in files:
        _check(name)
    out, ino = [], 1
    for d in _parents(files):
        out.append(_entry(ino, d, S_IFDIR | 0o755))
        ino += 1
    for name in sorted(files):
        data, perm = files[name]
        out.append(_entry(ino, name, S_IFREG | perm, data))
        ino += 1
    out.append(_entry(0, "TRAILER!!!", 0))
    return b"".join(out)
