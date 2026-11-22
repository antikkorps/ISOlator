import tempfile
import unittest
from pathlib import Path

from isolator.iso9660 import Iso
from isolator.profiles import casper_args, detect, readable_name
from tests.isobuilder import build_iso

EFI = {"EFI": {"BOOT": {"BOOTX64.EFI": b"efi"}}}

UBUNTU_LOOPBACK = b"""
menuentry "Try or Install Ubuntu" {
    set gfxpayload=keep
    linux  /casper/vmlinuz  iso-scan/filename=${iso_path} --- quiet splash
    initrd /casper/initrd
}
menuentry "Ubuntu (safe graphics)" {
    linux  /casper/vmlinuz nomodeset  iso-scan/filename=${iso_path} --- quiet splash
}
"""

MINT_GRUB = (b'menuentry "Start Linux Mint" --class linuxmint {\n'
             b"\tlinux\t/casper/vmlinuz  boot=casper uuid=6e72f523 username=mint "
             b"iso-scan/filename=${iso_path} quiet splash --\n\tinitrd\t/casper/initrd.lz\n}\n")


def fake_addon(iso):
    return b"ADDON"


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self, tree, rel="/x/test.iso", label="TESTISO"):
        path = build_iso(Path(self.tmp.name) / "t.iso", {**EFI, **tree}, label=label)
        with Iso(path) as iso:
            return detect(iso, rel, build_addon=fake_addon)

    def test_anaconda(self):
        r = self.detect({".treeinfo": b"[release]\nname = Rocky Linux\nversion = 10.3\nshort = Rocky\n",
                         "images": {"pxeboot": {"vmlinuz": b"k", "initrd.img": b"i"}}})
        self.assertEqual(r.title, "Rocky Linux 10.3 - install")
        self.assertEqual(r.css_class, "rocky")
        self.assertIn("inst.stage2=hd:LABEL=$isolabel:$iso", r.body)

    def test_fedora_live_uses_volume_label(self):
        r = self.detect({"LiveOS": {"squashfs.img": b"s"},
                         "images": {"pxeboot": {"vmlinuz": b"k", "initrd.img": b"i"}}},
                        rel="/Fedora-Workstation-Live-45-1.4.x86_64.iso", label="Fedora-WS-Live-45")
        self.assertIn("root=live:CDLABEL=Fedora-WS-Live-45", r.body)
        self.assertEqual(r.title, "Fedora Workstation Live 45 1.4 - live")

    def test_fedora_live_refuses_unsafe_label(self):
        r = self.detect({"LiveOS": {"squashfs.img": b"s"},
                         "images": {"pxeboot": {"vmlinuz": b"k", "initrd.img": b"i"}}}, label="a;reboot")
        self.assertTrue(r.refusal)

    def test_loopback(self):
        r = self.detect({"boot": {"grub": {"loopback.cfg": b"menuentry x {}"}}})
        self.assertIn("configfile /boot/grub/loopback.cfg", r.body)

    def test_ubuntu_casper(self):
        r = self.detect({"casper": {"vmlinuz": b"k", "initrd": b"i"},
                         "boot": {"grub": {"loopback.cfg": UBUNTU_LOOPBACK}}})
        self.assertEqual(r.addon, b"ADDON")
        self.assertIn("linux  (loop)/casper/vmlinuz iso-scan/filename=$iso --- quiet splash\n", r.body)
        self.assertIn("initrd (loop)/casper/initrd $addon\n", r.body)

    def test_mint_casper_reads_grub_cfg_through_loopback(self):
        r = self.detect({"casper": {"vmlinuz": b"k", "initrd.lz": b"i"},
                         "boot": {"grub": {"loopback.cfg": b"source /boot/grub/grub.cfg\n",
                                           "grub.cfg": MINT_GRUB}}})
        self.assertIn("boot=casper uuid=6e72f523 username=mint iso-scan/filename=$iso quiet splash --", r.body)
        self.assertIn("(loop)/casper/initrd.lz $addon", r.body)

    def test_injected_initrd_name_is_refused(self):
        evil = "initrd\n    chainloader /evil.efi\n    boot\n#"
        r = self.detect({"casper": {"vmlinuz": b"k", evil: b"i"},
                         "boot": {"grub": {"loopback.cfg": UBUNTU_LOOPBACK}}})
        self.assertTrue(r.refusal)
        self.assertNotIn("chainloader", r.body)

    def test_injected_treeinfo_class_falls_back(self):
        r = self.detect({".treeinfo": b'[release]\nname = R\nshort = x"}fi;reboot;if\n',
                         "images": {"pxeboot": {"vmlinuz": b"k", "initrd.img": b"i"}}})
        self.assertEqual(r.css_class, "redhat")

    def test_anaconda_without_initrd_is_refused(self):
        r = self.detect({".treeinfo": b"[release]\nname = R\n",
                         "images": {"pxeboot": {"vmlinuz": b"k"}}})
        self.assertTrue(r.refusal)

    def test_unknown_iso(self):
        self.assertIsNone(self.detect({"README": b"hi"}))


class CasperArgsTest(unittest.TestCase):
    def test_adds_iso_scan_when_missing(self):
        self.assertEqual(casper_args("linux /casper/vmlinuz --- quiet splash"),
                         "iso-scan/filename=$iso --- quiet splash")

    def test_refuses_unsafe_characters(self):
        for bad in ("linux /casper/vmlinuz quiet; reboot", "linux /casper/vmlinuz $(evil)",
                    'linux /casper/vmlinuz "x"', "linux /casper/vmlinuz a`b`"):
            with self.assertRaises(ValueError):
                casper_args(bad)

    def test_no_linux_line(self):
        with self.assertRaises(ValueError):
            casper_args("menuentry x {}")


class ReadableNameTest(unittest.TestCase):
    def test_strips_arch_and_separators(self):
        self.assertEqual(readable_name("linuxmint-22.3-cinnamon-64bit.iso"), "Linuxmint 22.3 cinnamon")


if __name__ == "__main__":
    unittest.main()
