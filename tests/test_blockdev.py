import unittest

from isolator.blockdev import DiskInfo, check_disk, parse_disk, root_names


def disk(**kw):
    base = dict(name="sdb", serial="ABC123", tran="usb", holds_root=False,
                rdev=(8, 16))
    base.update(kw)
    return DiskInfo(**base)


class CheckDiskTest(unittest.TestCase):
    def test_matching_usb_disk_is_accepted(self):
        self.assertIsNone(check_disk(disk(), "ABC123"))

    def test_wrong_serial_is_refused(self):
        # Two disks of the same model differ by a single character.
        self.assertIn("serial", check_disk(disk(serial="ABC12Q"), "ABC123"))

    def test_empty_expected_serial_is_refused(self):
        self.assertIn("serial", check_disk(disk(serial=""), ""))

    def test_non_usb_disk_is_refused(self):
        self.assertIn("USB", check_disk(disk(tran="nvme"), "ABC123"))

    def test_system_disk_is_refused(self):
        self.assertIn("system", check_disk(disk(holds_root=True), "ABC123"))


LSBLK_JSON = """{"blockdevices": [{"name": "sda", "serial": " CD99X ",
  "tran": "usb", "maj:min": "8:0"}]}"""


class ParseTest(unittest.TestCase):
    def test_raw_inverse_listing_gives_every_parent_disk(self):
        raw = "vg-root\nnvme0n1p3\nnvme0n1\n"
        self.assertEqual(root_names(raw), {"vg-root", "nvme0n1p3", "nvme0n1"})

    def test_parse_disk(self):
        info = parse_disk(LSBLK_JSON, root={"nvme0n1"})
        self.assertEqual(info, DiskInfo("sda", "CD99X", "usb", False, (8, 0)))

    def test_parse_disk_holding_root(self):
        self.assertTrue(parse_disk(LSBLK_JSON, root={"sda2", "sda"}).holds_root)


if __name__ == "__main__":
    unittest.main()
