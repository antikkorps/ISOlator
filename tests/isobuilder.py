"""Minimal ISO9660 image writer for tests.

Builds just enough of ECMA-119 (PVD, directory records, optional Rock Ridge
NM names) to exercise isolator.iso9660 without xorriso or genisoimage, which
are not installed by default on Debian.
"""
from __future__ import annotations

from pathlib import Path

SECTOR = 2048


def _both(n: int, width: int) -> bytes:
    """Both-endian field: ECMA-119 stores numbers LE then BE."""
    return n.to_bytes(width, "little") + n.to_bytes(width, "big")


def _record(name: bytes, lba: int, size: int, is_dir: bool, rr_name: str | None) -> bytes:
    su = b""
    if rr_name is not None:
        raw = rr_name.encode()
        su = b"NM" + bytes([5 + len(raw), 1, 0]) + raw
    pad = b"\0" if len(name) % 2 == 0 else b""
    length = 33 + len(name) + len(pad) + len(su)
    length += length % 2
    rec = (bytes([length, 0]) + _both(lba, 4) + _both(size, 4) + bytes(7)
           + bytes([2 if is_dir else 0, 0, 0]) + _both(1, 2)
           + bytes([len(name)]) + name + pad + su)
    return rec.ljust(length, b"\0")


def _iso_name(name: str, is_dir: bool) -> bytes:
    base = name.upper().replace("-", "_")
    return base.encode() if is_dir else (base + ";1").encode()


class _Node:
    def __init__(self, content):
        self.content = content
        self.is_dir = isinstance(content, dict)
        self.lba = 0
        self.size = SECTOR if self.is_dir else len(content)


def _allocate(tree: dict) -> tuple[_Node, list[_Node], int]:
    """Assign LBAs: directories first (one sector each), then files."""
    root = _Node(tree)
    dirs, files, stack = [], [], [root]
    while stack:
        node = stack.pop(0)
        dirs.append(node)
        node.children = {k: _Node(v) for k, v in node.content.items()}
        for child in node.children.values():
            (stack if child.is_dir else files).append(child)
    lba = 18
    for node in dirs + files:
        node.lba = lba
        lba += max(1, -(-node.size // SECTOR))
    return root, dirs + files, lba


def build_iso(path: Path, tree: dict, label: str = "TESTISO", rock_ridge: bool = True) -> Path:
    """Write an ISO9660 image of `tree` ({name: bytes | dict}) to `path`."""
    root, nodes, total = _allocate(tree)
    image = bytearray(total * SECTOR)
    for node in nodes:
        start = node.lba * SECTOR
        if node.is_dir:
            body = _record(b"\0", node.lba, SECTOR, True, None) + _record(b"\1", node.lba, SECTOR, True, None)
            for name, child in node.children.items():
                rr = name if rock_ridge else None
                body += _record(_iso_name(name, child.is_dir), child.lba, child.size, child.is_dir, rr)
            image[start:start + len(body)] = body
        else:
            image[start:start + node.size] = node.content
    pvd = bytearray(SECTOR)
    pvd[0:6] = b"\1CD001"
    pvd[40:72] = label.encode().ljust(32)
    pvd[156:190] = _record(b"\0", root.lba, SECTOR, True, None)
    image[16 * SECTOR:17 * SECTOR] = pvd
    image[17 * SECTOR:17 * SECTOR + 6] = b"\xffCD001"
    path.write_bytes(bytes(image))
    return path
