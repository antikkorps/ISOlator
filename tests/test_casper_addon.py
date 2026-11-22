import tempfile
import unittest
from pathlib import Path

from isolator.casper import changed_files, find_initrd_root, kernel_version, safe_path, snapshot


def make(root: Path, rel: str, data: bytes = b"") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class AddonPiecesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_main_archive_among_early_ones(self):
        make(self.dir, "early/kernel/x86/microcode/GenuineIntel.bin")
        make(self.dir, "main/scripts/casper-helpers")
        self.assertEqual(find_initrd_root(self.dir), self.dir / "main")

    def test_finds_root_of_single_archive(self):
        make(self.dir, "scripts/casper-helpers")
        self.assertEqual(find_initrd_root(self.dir), self.dir)

    def test_no_casper_is_an_error(self):
        make(self.dir, "init")
        with self.assertRaises(FileNotFoundError):
            find_initrd_root(self.dir)

    def test_kernel_version_needs_exactly_one(self):
        make(self.dir, "usr/lib/modules/7.0.0-30-generic/modules.dep")
        self.assertEqual(kernel_version(self.dir), "7.0.0-30-generic")
        make(self.dir, "usr/lib/modules/6.1.0/modules.dep")
        with self.assertRaises(ValueError):
            kernel_version(self.dir)

    def test_kernel_version_refuses_option_like_names(self):
        make(self.dir, "usr/lib/modules/-o..evil/modules.dep")
        with self.assertRaises(ValueError):
            kernel_version(self.dir)

    def test_kernel_version_refuses_symlinked_dir(self):
        (self.dir / "usr/lib/modules").mkdir(parents=True)
        (self.dir / "usr/lib/modules/6.8.0").symlink_to(Path.home())
        with self.assertRaises(ValueError):
            kernel_version(self.dir)

    def test_safe_path_refuses_symlinks_anywhere(self):
        make(self.dir, "real/file", b"x")
        (self.dir / "link").symlink_to(self.dir / "real")
        (self.dir / "real/out").symlink_to("/etc/passwd")
        self.assertEqual(safe_path(self.dir, "real/file"), self.dir / "real/file")
        for rel in ("link/file", "real/out", "../x"):
            with self.assertRaises(ValueError):
                safe_path(self.dir, rel)

    def test_changed_files_reports_new_and_modified_only(self):
        mods = self.dir / "usr/lib/modules/1"
        make(mods, "modules.dep", b"old")
        make(mods, "modules.builtin", b"same")
        before = snapshot(mods)
        make(mods, "modules.dep", b"new")
        make(mods, "modules.alias.bin", b"bin")
        self.assertEqual(changed_files(mods, before), ["modules.alias.bin", "modules.dep"])


if __name__ == "__main__":
    unittest.main()
