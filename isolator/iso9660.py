"""Minimal read-only ISO9660 reader (ECMA-119 + Rock Ridge NM names).

Reading the image directly avoids mounting it, which would need root, and
avoids depending on external tools such as 7z or xorriso.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

SECTOR = 2048


class Entry(NamedTuple):
    name: str
    lba: int
    size: int
    is_dir: bool


def _rock_ridge_name(rec: bytes, start: int) -> bytes:
    """Concatenate NM entries of the System Use area (long Linux names)."""
    name, pos = b"", start
    while pos + 4 <= len(rec):
        sig, length = rec[pos:pos + 2], rec[pos + 2]
        if length < 4:
            break
        if sig == b"NM":
            name += rec[pos + 5:pos + length]
        pos += length
    return name


def parse_record(rec: bytes) -> Entry:
    name_len = rec[32]
    iso_name = rec[33:33 + name_len]
    # The System Use area follows the name, padded to an even offset.
    rr = _rock_ridge_name(rec, 33 + name_len + (1 - name_len % 2))
    if rr:
        name = rr.decode("utf-8", "replace")
    else:
        name = iso_name.decode("ascii", "replace").split(";")[0].rstrip(".")
    return Entry(name, int.from_bytes(rec[2:6], "little"),
                 int.from_bytes(rec[10:14], "little"), bool(rec[25] & 0x02))


def parse_directory(data: bytes) -> dict[str, Entry]:
    entries, pos = {}, 0
    while pos < len(data):
        length = data[pos]
        if length == 0:  # records never cross sectors: skip the padding
            pos = (pos // SECTOR + 1) * SECTOR
            continue
        rec = data[pos:pos + length]
        pos += length
        if rec[32] == 1 and rec[33] in (0, 1):  # "." and ".."
            continue
        entry = parse_record(rec)
        entries[entry.name.lower()] = entry
    return entries


class Iso:
    """Lookups are case-insensitive; only the directories on a requested
    path are read, so large images are cheap to inspect."""

    def __init__(self, path: Path):
        self.path = path
        self._f = open(path, "rb")
        try:
            pvd = self._read_at(16, SECTOR)
            if len(pvd) < 190 or pvd[0] != 1 or pvd[1:6] != b"CD001":
                raise ValueError("not an ISO9660 file system")
        except Exception:
            self._f.close()
            raise
        self._label = pvd[40:72].decode("ascii", "replace").strip()
        root = parse_record(pvd[156:190])
        self._root = Entry("", root.lba, root.size, True)
        self._cache: dict[tuple[int, int], dict[str, Entry]] = {}

    def __enter__(self) -> Iso:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._f.close()

    def _read_at(self, lba: int, size: int) -> bytes:
        self._f.seek(lba * SECTOR)
        return self._f.read(size)

    def _list(self, d: Entry) -> dict[str, Entry]:
        key = (d.lba, d.size)
        if key not in self._cache:
            self._cache[key] = parse_directory(self._read_at(d.lba, d.size))
        return self._cache[key]

    def _walk(self, path: str) -> list[Entry] | None:
        """Entries along `path`, or None if any component is missing."""
        current, found = self._root, []
        for part in path.strip("/").split("/"):
            if not current.is_dir:
                return None
            current = self._list(current).get(part.lower())
            if current is None:
                return None
            found.append(current)
        return found

    def has(self, path: str) -> bool:
        return self._walk(path) is not None

    def real_name(self, path: str) -> str:
        """`path` with the exact case recorded in the image."""
        entries = self._walk(path)
        if entries is None:
            raise FileNotFoundError(path)
        return "/".join(e.name for e in entries)

    def _file(self, path: str) -> Entry:
        entries = self._walk(path)
        if entries is None or entries[-1].is_dir:
            raise FileNotFoundError(path)
        return entries[-1]

    def read(self, path: str, limit: int = 1 << 20) -> str:
        e = self._file(path)
        return self._read_at(e.lba, min(e.size, limit)).decode("utf-8", "replace")

    def offset(self, path: str) -> int:
        """Byte offset of the file's data in the image (files are contiguous
        in ISO9660), so tools like unsquashfs can read it in place."""
        return self._file(path).lba * SECTOR

    def extract(self, path: str, dest: Path, chunk: int = 1 << 20) -> None:
        e = self._file(path)
        self._f.seek(e.lba * SECTOR)
        with open(dest, "wb") as out:
            left = e.size
            while left:
                data = self._f.read(min(chunk, left))
                if not data:
                    raise ValueError(f"{path}: truncated image")
                out.write(data)
                left -= len(data)

    def list_dir(self, path: str) -> list[str]:
        entries = self._walk(path)
        if entries is None or not entries[-1].is_dir:
            raise NotADirectoryError(path)
        return [e.name for e in self._list(entries[-1]).values()]

    def label(self) -> str:
        return self._label
