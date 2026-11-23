import subprocess
import tempfile
import unittest
from pathlib import Path

from isolator.config import MenuConfig
from isolator.menu import addon_name, analyse, arrange, entry, render, settings, write
from isolator.profiles import Result
from tests.isobuilder import build_iso

EFI = {"EFI": {"BOOT": {"BOOTX64.EFI": b"efi"}}}
LOOPBACK = {**EFI, "boot": {"grub": {"loopback.cfg": b"menuentry x {}"}}}
CASPER = {**EFI, "casper": {"vmlinuz": b"k", "initrd": b"i"},
          "boot": {"grub": {"loopback.cfg": b"linux /casper/vmlinuz --- quiet\n"}}}


class EntryTest(unittest.TestCase):
    def test_entry_is_conditional_on_the_iso(self):
        out = entry("/a/b.iso", Result(title='Bad "title" $x', css_class="arch", body="    x\n"))
        self.assertIn("if [ -f ($isopart)$iso ]; then", out)
        self.assertIn('menuentry "Bad title x" --class arch --id /a/b.iso {', out)
        self.assertNotIn("addon", out)

    def test_entry_with_addon(self):
        out = entry("/x86_64/ubuntu.iso", Result(title="U", css_class="ubuntu", body="", addon=b"A"))
        self.assertIn(f"    set addon=($isopart)/multiboot/addons/{addon_name('/x86_64/ubuntu.iso')}\n", out)

    def test_addon_name_is_unique_per_path(self):
        self.assertNotEqual(addon_name("/a_b.iso"), addon_name("/a/b.iso"))
        self.assertRegex(addon_name("/x86_64/ubuntu-26.04.iso"), r"^ubuntu-26\.04-[0-9a-f]{12}\.img$")

    def test_render_passes_grub_script_check(self):
        menu = render([("/a.iso", Result(title="A", css_class="a", body="    linux (loop)/k\n", addon=b"x"))])
        with tempfile.NamedTemporaryFile("w", suffix=".cfg") as f:
            f.write(menu)
            f.flush()
            subprocess.run(["grub-script-check", f.name], check=True)


def results(*rels_titles):
    return [(rel, Result(title=title, css_class="x", body="")) for rel, title in rels_titles]


class EntryIdTest(unittest.TestCase):
    def test_entry_has_the_iso_path_as_id(self):
        out = entry("/a/b.iso", Result(title="B", css_class="arch", body=""))
        self.assertIn('menuentry "B" --class arch --id /a/b.iso {', out)


class ArrangeTest(unittest.TestCase):
    KEPT = results(("/x/arch.iso", "Arch"), ("/x/mint.iso", "Mint"),
                   ("/x/ubuntu.iso", "Ubuntu"), ("/old/fedora.iso", "Fedora"))

    def rels(self, entries):
        return [rel for rel, _ in entries]

    def test_no_config_keeps_title_order(self):
        shown, hidden = arrange(self.KEPT, MenuConfig())
        self.assertEqual(self.rels(shown), self.rels(self.KEPT))
        self.assertEqual(hidden, [])

    def test_order_patterns_come_first_in_pattern_order(self):
        shown, _ = arrange(self.KEPT, MenuConfig(order=("/x/u*", "/x/m*")))
        self.assertEqual(self.rels(shown), ["/x/ubuntu.iso", "/x/mint.iso",
                                            "/x/arch.iso", "/old/fedora.iso"])

    def test_patterns_ignore_case(self):
        # exFAT is case-insensitive: "/X/UBUNTU*" names the same file.
        shown, _ = arrange(self.KEPT, MenuConfig(order=("/X/UBUNTU*",)))
        self.assertEqual(self.rels(shown)[0], "/x/ubuntu.iso")

    def test_hidden_entries_are_removed(self):
        shown, hidden = arrange(self.KEPT, MenuConfig(hidden=("/old/*",)))
        self.assertNotIn("/old/fedora.iso", self.rels(shown))
        self.assertEqual(hidden, ["/old/fedora.iso"])


    def test_hidden_wins_over_order(self):
        shown, hidden = arrange(self.KEPT, MenuConfig(order=("/old/*",), hidden=("/old/*",)))
        self.assertNotIn("/old/fedora.iso", self.rels(shown))
        self.assertEqual(hidden, ["/old/fedora.iso"])


class SettingsTest(unittest.TestCase):
    def test_default_ignores_case_like_exfat(self):
        # GRUB compares ids exactly: the real path must be written.
        out = settings(MenuConfig(default="/X/Ubuntu.iso"), {"/x/ubuntu.iso"})
        self.assertIn("set default=/x/ubuntu.iso\n", out)

    def test_nothing_without_config(self):
        self.assertEqual(settings(MenuConfig(), {"/a.iso"}), "")

    def test_timeout_and_default(self):
        out = settings(MenuConfig(timeout=10, default="/a.iso"), {"/a.iso"})
        self.assertIn("set timeout=10\n", out)
        self.assertIn("set default=/a.iso\n", out)

    def test_default_not_in_menu_is_left_out(self):
        self.assertNotIn("default", settings(MenuConfig(default="/gone.iso"), {"/a.iso"}))

    def test_render_with_settings_passes_grub_script_check(self):
        menu = render(results(("/a.iso", "A")), MenuConfig(timeout=5, default="/a.iso"))
        self.assertIn("set default=/a.iso", menu)
        with tempfile.NamedTemporaryFile("w", suffix=".cfg") as f:
            f.write(menu)
            f.flush()
            subprocess.run(["grub-script-check", f.name], check=True)


class DiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "multiboot").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyse_sorts_kept_and_skipped(self):
        build_iso(self.root / "arch.iso", LOOPBACK)
        build_iso(self.root / "has space.iso", LOOPBACK)
        build_iso(self.root / "arm.iso", {"boot": {"grub": {"loopback.cfg": b""}}})
        (self.root / "junk.iso").write_bytes(b"\0" * 40000)
        kept, skipped = analyse(self.root, build_addon=lambda iso: b"")
        self.assertEqual([rel for rel, _ in kept], ["/arch.iso"])
        self.assertEqual(sorted(rel for rel, _ in skipped), ["/arm.iso", "/has space.iso", "/junk.iso"])

    def test_uppercase_extension_is_found(self):
        build_iso(self.root / "ARCH.ISO", LOOPBACK)
        kept, _ = analyse(self.root, build_addon=lambda iso: b"")
        self.assertEqual([rel for rel, _ in kept], ["/ARCH.ISO"])

    def test_write_saves_menu_backup_and_addons(self):
        build_iso(self.root / "ubuntu.iso", CASPER)
        kept, _ = analyse(self.root, build_addon=lambda iso: b"ADDON")
        (self.root / "multiboot/menu.cfg").write_text("old")
        write(self.root, kept)
        self.assertIn("set addon=", (self.root / "multiboot/menu.cfg").read_text())
        self.assertEqual((self.root / "multiboot/menu.cfg.bak").read_text(), "old")
        self.assertEqual((self.root / "multiboot/addons" / addon_name("/ubuntu.iso")).read_bytes(), b"ADDON")


if __name__ == "__main__":
    unittest.main()
