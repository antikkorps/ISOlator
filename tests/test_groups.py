import subprocess
import tempfile
import unittest

from isolator.config import MenuConfig, Submenu
from isolator.groups import entry_ids, group
from isolator.menu import render
from isolator.profiles import Result


def res(category):
    return Result(title="T", css_class="x", body="    linux (loop)/k\n", category=category)


KEPT = [("/x/rocky.iso", res("install")), ("/x/ubuntu.iso", res("live")),
        ("/tools/gparted.iso", res("live")), ("/x/alma.iso", res("install"))]
TOOLS = Submenu("Tools", ("/tools/*",))


def rels(entries):
    return [rel for rel, _ in entries]


class GroupTest(unittest.TestCase):
    def test_no_config_keeps_everything_at_top_level(self):
        top, groups = group(KEPT, MenuConfig())
        self.assertEqual(rels(top), rels(KEPT))
        self.assertEqual(groups, [])

    def test_custom_submenu_alone_leaves_the_rest_at_top_level(self):
        top, groups = group(KEPT, MenuConfig(submenu=(TOOLS,)))
        self.assertEqual(rels(top), ["/x/rocky.iso", "/x/ubuntu.iso", "/x/alma.iso"])
        self.assertEqual([(g.title, rels(g.entries)) for g in groups],
                         [("Tools", ["/tools/gparted.iso"])])

    def test_automatic_submenus_by_category_keep_the_arranged_order(self):
        top, groups = group(KEPT, MenuConfig(submenus=True))
        self.assertEqual(top, [])
        self.assertEqual([(g.title, rels(g.entries)) for g in groups],
                         [("Installers", ["/x/rocky.iso", "/x/alma.iso"]),
                          ("Live systems", ["/x/ubuntu.iso", "/tools/gparted.iso"])])

    def test_custom_submenus_win_over_categories_and_come_after(self):
        _, groups = group(KEPT, MenuConfig(submenus=True, submenu=(TOOLS,)))
        self.assertEqual([g.title for g in groups], ["Installers", "Live systems", "Tools"])
        self.assertEqual(rels(groups[1].entries), ["/x/ubuntu.iso"])

    def test_first_matching_submenu_wins_and_patterns_ignore_case(self):
        both = (Submenu("A", ("/X/*",)), Submenu("B", ("/x/rocky.iso",)))
        _, groups = group(KEPT, MenuConfig(submenu=both))
        self.assertEqual([g.title for g in groups], ["A"])

    def test_empty_submenus_are_left_out(self):
        _, groups = group(KEPT[1:3], MenuConfig(submenus=True, submenu=(Submenu("E", ("/none/*",)),)))
        self.assertEqual([g.title for g in groups], ["Live systems"])

    def test_ids_are_unique_and_safe(self):
        _, groups = group(KEPT, MenuConfig(submenus=True, submenu=(TOOLS,)))
        ids = [g.id for g in groups]
        self.assertEqual(len(set(ids)), len(ids))
        for i in ids:
            self.assertRegex(i, r"^isolator-[a-z0-9-]+\Z")


class EntryIdsTest(unittest.TestCase):
    def test_entries_in_a_submenu_are_reached_through_it(self):
        top, groups = group(KEPT, MenuConfig(submenu=(TOOLS,)))
        ids = entry_ids(top, groups)
        self.assertEqual(ids["/x/rocky.iso"], "/x/rocky.iso")
        self.assertEqual(ids["/tools/gparted.iso"], f"{groups[0].id}>/tools/gparted.iso")


class RenderSubmenuTest(unittest.TestCase):
    def test_default_inside_a_submenu(self):
        menu = render(KEPT, MenuConfig(submenus=True, default="/X/Ubuntu.iso"))
        self.assertIn('set default="isolator-live>/x/ubuntu.iso"\n', menu)

    def test_default_inside_a_custom_submenu_with_order(self):
        cfg = MenuConfig(submenu=(TOOLS,), order=("/tools/*",), default="/tools/gparted.iso")
        self.assertIn('set default="isolator-submenu-1>/tools/gparted.iso"\n', render(KEPT, cfg))

    def test_submenu_block_holds_its_entries(self):
        menu = render(KEPT, MenuConfig(submenu=(TOOLS,)))
        tools = menu.index('submenu "Tools" --class submenu --id isolator-submenu-1 {')
        self.assertLess(menu.index("--id /x/alma.iso"), tools)
        self.assertGreater(menu.index("--id /tools/gparted.iso"), tools)

    def test_render_with_submenus_passes_grub_script_check(self):
        menu = render(KEPT, MenuConfig(submenus=True, submenu=(TOOLS,), default="/x/rocky.iso"))
        with tempfile.NamedTemporaryFile("w", suffix=".cfg") as f:
            f.write(menu)
            f.flush()
            subprocess.run(["grub-script-check", f.name], check=True)
