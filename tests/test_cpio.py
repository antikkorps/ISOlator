import subprocess
import tempfile
import unittest
from pathlib import Path

from isolator.cpio import build_newc


class CpioTest(unittest.TestCase):
    def test_archive_extracts_with_system_cpio(self):
        files = {
            "scripts/casper-helpers": (b"#!/bin/sh\necho hi\n", 0o755),
            "usr/lib/modules/1.0/kernel/fs/exfat/exfat.ko.zst": (b"\x28\xb5\x2f\xfd" + b"z" * 1001, 0o644),
        }
        archive = build_newc(files)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["cpio", "-id", "--quiet"], input=archive, cwd=tmp, check=True)
            for name, (data, mode) in files.items():
                path = Path(tmp) / name
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(path.stat().st_mode & 0o777, mode)

    def test_parent_directories_are_listed_once_before_files(self):
        archive = build_newc({"a/b/c": (b"x", 0o644), "a/b/d": (b"y", 0o644)})
        names = subprocess.run(["cpio", "-t", "--quiet"], input=archive,
                               capture_output=True, check=True).stdout.decode().split()
        self.assertEqual(names, ["a", "a/b", "a/b/c", "a/b/d"])

    def test_rejects_unsafe_paths(self):
        for bad in ("/abs", "../up", "a/../b", ""):
            with self.assertRaises(ValueError):
                build_newc({bad: (b"", 0o644)})


if __name__ == "__main__":
    unittest.main()
