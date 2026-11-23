import unittest
from pathlib import Path

from isolator.qemu import VmSpec, default_memory, qemu_command


def spec(**kw):
    base = dict(device_fd=7, vars_file=Path("/tmp/vars.fd"), memory_mb=4096,
                target=None, kvm=True)
    base.update(kw)
    return VmSpec(**base)


def option_values(argv, flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


class QemuCommandTest(unittest.TestCase):
    def test_usb_disk_is_passed_as_read_only_inherited_fd(self):
        argv = qemu_command(spec())
        self.assertIn("fd=7,set=1,opaque=isolator-ro", option_values(argv, "-add-fd"))
        blockdevs = option_values(argv, "-blockdev")
        self.assertTrue(blockdevs)
        for b in blockdevs:
            if "fdset" in b or "node-name=usb" in b:
                self.assertIn("read-only=on", b)
        self.assertTrue(any("driver=host_device" in b and "/dev/fdset/1" in b
                            for b in blockdevs))

    def test_usb_disk_is_the_first_boot_device(self):
        devices = option_values(qemu_command(spec()), "-device")
        self.assertIn("usb-storage,drive=usb,bootindex=0", devices)

    def test_firmware_code_is_read_only_and_vars_are_the_copy(self):
        drives = option_values(qemu_command(spec()), "-drive")
        code = [d for d in drives if "unit=0" in d]
        self.assertEqual(len(code), 1)
        self.assertIn("readonly=on", code[0])
        self.assertTrue(any("unit=1" in d and "file=/tmp/vars.fd" in d for d in drives))

    def test_no_target_disk_by_default(self):
        argv = qemu_command(spec())
        self.assertFalse(any("target" in a for a in argv))

    def test_target_disk_is_writable_qcow2(self):
        argv = qemu_command(spec(target=Path("/home/u/t.qcow2")))
        drives = option_values(argv, "-drive")
        self.assertIn("if=none,id=target,format=qcow2,file=/home/u/t.qcow2", drives)
        self.assertIn("virtio-blk-pci,drive=target,bootindex=1",
                      option_values(argv, "-device"))

    def test_commas_in_target_path_are_escaped(self):
        # Unescaped, "x,format=raw" would inject a QEMU suboption.
        drives = option_values(qemu_command(spec(target=Path("/t/x,format=raw"))), "-drive")
        self.assertIn("if=none,id=target,format=qcow2,file=/t/x,,format=raw", drives)

    def test_accelerator_falls_back_to_tcg(self):
        self.assertIn("q35,accel=kvm", option_values(qemu_command(spec()), "-machine"))
        self.assertIn("q35,accel=tcg",
                      option_values(qemu_command(spec(kvm=False)), "-machine"))

    def test_memory(self):
        self.assertEqual(option_values(qemu_command(spec(memory_mb=2048)), "-m"), ["2048"])



class DefaultMemoryTest(unittest.TestCase):
    MEMINFO = "MemTotal:        3819520 kB\nMemFree:          121000 kB\n"

    def test_half_of_a_small_host(self):
        # A 3.7 GB host given a 4 GB guest swaps the whole installation.
        self.assertEqual(default_memory(self.MEMINFO), 1865)

    def test_capped_at_4096_on_a_large_host(self):
        self.assertEqual(default_memory("MemTotal: 33554432 kB\n"), 4096)


if __name__ == "__main__":
    unittest.main()
