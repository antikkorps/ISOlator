import tempfile
import unittest
from pathlib import Path

from isolator.iso9660 import Iso
from tests.isobuilder import build_iso

TREE = {
    "EFI": {"BOOT": {"BOOTX64.EFI": b"efi"}},
    "casper": {"vmlinuz": b"kernel", "initrd": b"x" * 5000},
    ".treeinfo": b"[release]\nname = Rocky\n",
}


class IsoReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = build_iso(Path(self.tmp.name) / "t.iso", TREE, label="MY_LABEL")

    def tearDown(self):
        self.tmp.cleanup()

    def test_label(self):
        with Iso(self.path) as iso:
            self.assertEqual(iso.label(), "MY_LABEL")

    def test_has_is_case_insensitive(self):
        with Iso(self.path) as iso:
            self.assertTrue(iso.has("efi/boot/bootx64.efi"))
            self.assertTrue(iso.has("casper/vmlinuz"))
            self.assertFalse(iso.has("casper/missing"))
            self.assertFalse(iso.has("casper/vmlinuz/below_a_file"))

    def test_real_name_keeps_recorded_case(self):
        with Iso(self.path) as iso:
            self.assertEqual(iso.real_name("efi/boot/bootx64.efi"), "EFI/BOOT/BOOTX64.EFI")

    def test_read_spans_several_sectors(self):
        with Iso(self.path) as iso:
            self.assertEqual(iso.read("casper/initrd"), "x" * 5000)
            self.assertIn("Rocky", iso.read(".treeinfo"))

    def test_offset_points_at_file_content(self):
        with Iso(self.path) as iso:
            off = iso.offset("casper/vmlinuz")
        with open(self.path, "rb") as f:
            f.seek(off)
            self.assertEqual(f.read(6), b"kernel")

    def test_extract_copies_file(self):
        dest = Path(self.tmp.name) / "initrd"
        with Iso(self.path) as iso:
            iso.extract("casper/initrd", dest)
        self.assertEqual(dest.read_bytes(), b"x" * 5000)

    def test_list_dir(self):
        with Iso(self.path) as iso:
            self.assertEqual(sorted(iso.list_dir("casper")), ["initrd", "vmlinuz"])

    def test_without_rock_ridge_falls_back_to_iso_names(self):
        path = build_iso(Path(self.tmp.name) / "plain.iso", TREE, rock_ridge=False)
        with Iso(path) as iso:
            self.assertTrue(iso.has("casper/vmlinuz"))

    def test_rejects_non_iso(self):
        bad = Path(self.tmp.name) / "bad.iso"
        bad.write_bytes(bytes(40000))
        with self.assertRaises(ValueError):
            Iso(bad)


if __name__ == "__main__":
    unittest.main()
