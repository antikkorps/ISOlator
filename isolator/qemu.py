"""Build the QEMU command line that boots the ISOlator disk under OVMF.

The USB disk reaches QEMU only as an already-open read-only file descriptor
(QEMU fd set): QEMU never opens the device itself, so it cannot write to it
whatever the guest does.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

OVMF_CODE = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
OVMF_VARS = Path("/usr/share/OVMF/OVMF_VARS_4M.fd")
FDSET = 1


@dataclass(frozen=True)
class VmSpec:
    device_fd: int
    vars_file: Path
    memory_mb: int
    target: Path | None
    kvm: bool


def _firmware(vars_file: Path) -> list[str]:
    return ["-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={OVMF_CODE}",
            "-drive", f"if=pflash,format=raw,unit=1,file={_escape(vars_file)}"]


def _usb_disk(fd: int) -> list[str]:
    # host_device must be explicit: QEMU cannot probe a /dev/fdset path.
    return ["-add-fd", f"fd={fd},set={FDSET},opaque=isolator-ro",
            "-blockdev", f"driver=host_device,node-name=usbdev,"
                         f"filename=/dev/fdset/{FDSET},read-only=on",
            "-blockdev", "driver=raw,node-name=usb,file=usbdev,read-only=on",
            "-device", "qemu-xhci",
            "-device", "usb-storage,drive=usb,bootindex=0"]


def _escape(value: object) -> str:
    # QEMU option values escape a comma by doubling it.
    return str(value).replace(",", ",,")


def _target_disk(target: Path) -> list[str]:
    return ["-drive", f"if=none,id=target,format=qcow2,file={_escape(target)}",
            "-device", "virtio-blk-pci,drive=target,bootindex=1"]


def qemu_command(spec: VmSpec) -> list[str]:
    accel = "kvm" if spec.kvm else "tcg"
    argv = ["qemu-system-x86_64", "-machine", f"q35,accel={accel}",
            "-cpu", "host" if spec.kvm else "max", "-smp", "2",
            "-m", str(spec.memory_mb), "-nic", "user,model=virtio-net-pci",
            *_firmware(spec.vars_file), *_usb_disk(spec.device_fd)]
    if spec.target is not None:
        argv += _target_disk(spec.target)
    return argv
