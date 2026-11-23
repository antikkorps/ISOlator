#!/usr/bin/env python3
"""qemu-test.py - boot the ISOlator USB disk in a QEMU/OVMF virtual machine.

The USB disk is passed to QEMU read-only: only the open() of the device runs
as root (sudo asks for your password), QEMU runs as you. Use it to try a
full installation onto a virtual disk, or to preview the menu, without
rebooting the PC.

Usage:
    ./qemu-test.py /dev/sdX "<serial>"                      # boot the menu only
    ./qemu-test.py /dev/sdX "<serial>" --target disk.qcow2  # + install target

The serial is required, as for install-multiboot.sh:
    lsblk -o NAME,SERIAL,TRAN,SIZE
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from isolator.blockdev import check_disk, read_disk
from isolator.privfd import open_readonly_as_root
from isolator.qemu import OVMF_VARS, VmSpec, qemu_command


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("device", type=Path)
    p.add_argument("serial", help="expected serial of the USB disk")
    p.add_argument("--target", type=Path,
                   help="qcow2 install target, created if missing")
    p.add_argument("--target-size", default="40G")
    p.add_argument("--memory", type=int, default=4096, help="MiB")
    return p.parse_args()


def ensure_target(target: Path, size: str) -> None:
    if not target.exists():
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2",
                        str(target), size], check=True)


def run_vm(args: argparse.Namespace, fd: int) -> int:
    # A fresh copy of the UEFI variables each run: the guest's boot entries
    # never leak from one test into the next.
    with tempfile.TemporaryDirectory(prefix="isolator-qemu-") as tmp:
        vars_file = Path(tmp) / "OVMF_VARS.fd"
        shutil.copyfile(OVMF_VARS, vars_file)
        spec = VmSpec(device_fd=fd, vars_file=vars_file, memory_mb=args.memory,
                      target=args.target,
                      kvm=os.access("/dev/kvm", os.R_OK | os.W_OK))
        return subprocess.run(qemu_command(spec), pass_fds=(fd,)).returncode


def checked_disk(device: Path, serial: str):
    info = read_disk(device)
    problem = check_disk(info, serial)
    if problem:
        sys.exit(f"ERROR: {problem}. Stopping.")
    return info


def acquire_disk(device: Path, serial: str) -> int:
    """Return a read-only fd on the disk, checked before and after opening."""
    info = checked_disk(device, serial)
    fd = open_readonly_as_root(device, info.rdev)
    # Checked again while the fd is held: the kernel cannot give this
    # major:minor to another disk now, so a disk swapped during the sudo
    # prompt is caught here.
    if checked_disk(device, serial).rdev != info.rdev:
        os.close(fd)
        sys.exit(f"ERROR: {device} changed while it was being opened. Stopping.")
    return fd


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        sys.exit("ERROR: run it as your user, not with sudo (it asks itself)")
    if not args.device.is_block_device():
        sys.exit(f"ERROR: {args.device} is not a block device")
    try:
        if args.target:
            ensure_target(args.target, args.target_size)
        fd = acquire_disk(args.device, args.serial)
    except (subprocess.CalledProcessError, OSError) as e:
        sys.exit(f"ERROR: {e}")
    try:
        return run_vm(args, fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
