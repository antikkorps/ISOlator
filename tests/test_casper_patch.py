import unittest

from isolator.casper import PatchError, patch_helpers

HELPERS = """\
is_supported_fs(){
    [ -z "${1}" ] && return 1
    case ${1} in
        ext2|ext3|ext4|xfs|jfs|reiserfs|vfat|ntfs|iso9660|btrfs|udf)
            return 0
            ;;
    esac
    return 1
}

wait_for_devs(){
    udevadm settle
    modprobe ext3
    modprobe ext4
    modprobe reiserfs
}
"""


class PatchHelpersTest(unittest.TestCase):
    def test_exfat_becomes_a_supported_fs(self):
        out = patch_helpers(HELPERS)
        self.assertIn("        exfat|ext2|ext3|ext4|xfs|", out)

    def test_exfat_module_is_loaded_with_the_others(self):
        out = patch_helpers(HELPERS)
        self.assertIn("    modprobe ext4\n    modprobe exfat\n", out)

    def test_nothing_else_changes(self):
        out = patch_helpers(HELPERS)
        removed = out.replace("exfat|", "", 1).replace("    modprobe exfat\n", "", 1)
        self.assertEqual(removed, HELPERS)

    def test_refuses_unknown_layout(self):
        with self.assertRaises(PatchError):
            patch_helpers(HELPERS.replace("ext2|ext3|ext4", "ext4"))
        with self.assertRaises(PatchError):
            patch_helpers(HELPERS.replace("    modprobe ext4\n", ""))

    def test_refuses_ambiguous_layout(self):
        with self.assertRaises(PatchError):
            patch_helpers(HELPERS + HELPERS)


if __name__ == "__main__":
    unittest.main()
