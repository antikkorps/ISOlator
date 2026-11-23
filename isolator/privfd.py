"""Get a read-only descriptor on a block device with the smallest root step.

Only an `open(O_RDONLY)` runs as root (through sudo); the descriptor comes
back over a Unix socket (SCM_RIGHTS) and everything else, QEMU included,
runs as the user. A read-only descriptor cannot be turned into a writable
one, so the kernel itself guarantees the disk is never written.
"""
from __future__ import annotations

import fcntl
import os
import socket
import stat
import subprocess
from pathlib import Path

# Runs as root: open, send, nothing else. -I keeps the cwd and user site
# packages out of root's import path.
_ROOT_HELPER = (
    "import os, socket, sys\n"
    "s = socket.socket(fileno=0)\n"
    "fd = os.open(sys.argv[1], os.O_RDONLY | os.O_CLOEXEC)\n"
    "socket.send_fds(s, [b'fd'], [fd])\n"
)


def same_device(expected: tuple[int, int], rdev: int) -> bool:
    return expected == (os.major(rdev), os.minor(rdev))


def fd_problem(fd: int, expected: tuple[int, int]) -> str | None:
    """Return why the descriptor is not the expected read-only device."""
    if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        return "the descriptor is not read-only"
    st = os.fstat(fd)
    if not stat.S_ISBLK(st.st_mode):
        return "the descriptor is not a block device"
    if not same_device(expected, st.st_rdev):
        return "the descriptor is not the disk that was checked"
    return None


def open_readonly_as_root(device: Path, expected: tuple[int, int]) -> int:
    """Open `device` read-only through sudo and return the verified fd.

    `expected` is the major:minor of the disk that passed the guard rails.
    """
    ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with ours, theirs:
        subprocess.run(["sudo", "--", "/usr/bin/python3", "-I", "-c",
                        _ROOT_HELPER, str(device)], stdin=theirs, check=True)
        _, fds, _, _ = socket.recv_fds(ours, 16, 1)
    if len(fds) != 1:
        raise OSError("sudo helper returned no descriptor")
    problem = fd_problem(fds[0], expected)
    if problem:
        os.close(fds[0])
        raise OSError(problem)
    return fds[0]
