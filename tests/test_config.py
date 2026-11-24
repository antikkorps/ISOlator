import json
import tempfile
import unittest
from pathlib import Path

from isolator.config import ConfigError, MenuConfig, Submenu, load_config, parse_config


class ParseConfigTest(unittest.TestCase):
    def test_empty_file_gives_defaults(self):
        self.assertEqual(parse_config(""), MenuConfig())

    def test_full_menu_section(self):
        cfg = parse_config('[menu]\ntimeout = 10\ndefault = "/x86_64/u.iso"\n'
                           'order = ["/x86_64/u*"]\nhidden = ["/old/*"]\n')
        self.assertEqual(cfg, MenuConfig(timeout=10, default="/x86_64/u.iso",
                                         order=("/x86_64/u*",), hidden=("/old/*",)))

    def test_wait_forever(self):
        self.assertEqual(parse_config("[menu]\ntimeout = -1\n").timeout, -1)

    def assertRefused(self, text, word):
        with self.assertRaises(ConfigError) as ctx:
            parse_config(text)
        self.assertIn(word, str(ctx.exception))

    def test_invalid_toml(self):
        self.assertRefused("[menu\n", "TOML")

    def test_unknown_key_is_refused(self):
        # A typo must not be silently ignored.
        self.assertRefused("[menu]\ntimout = 5\n", "timout")

    def test_unknown_section_is_refused(self):
        self.assertRefused("[menus]\n", "menus")

    def test_timeout_must_be_an_integer(self):
        self.assertRefused('[menu]\ntimeout = "5"\n', "timeout")
        self.assertRefused("[menu]\ntimeout = true\n", "timeout")
        self.assertRefused("[menu]\ntimeout = -2\n", "timeout")

    def test_default_reaches_grub_so_it_is_whitelisted(self):
        self.assertRefused('[menu]\ndefault = "/a.iso; reboot"\n', "default")
        self.assertRefused('[menu]\ndefault = "a.iso"\n', "default")

    def test_default_with_trailing_newline_is_refused(self):
        self.assertRefused('[menu]\ndefault = "/a.iso\\n"\n', "default")

    def test_menu_must_be_a_table(self):
        self.assertRefused("menu = 1\n", "table")

    def test_patterns_must_start_with_a_slash(self):
        # "ubuntu-*" would silently match nothing: paths start with "/".
        self.assertRefused('[menu]\norder = ["ubuntu-*"]\n', "order")

    def test_patterns_must_be_a_list_of_strings(self):
        self.assertRefused('[menu]\norder = "/a*"\n', "order")
        self.assertRefused("[menu]\nhidden = [1]\n", "hidden")


class LoadConfigTest(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_config(Path("/nonexistent/isolator.toml")), MenuConfig())

    def test_error_names_the_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml") as f:
            f.write("[menu]\nbad = 1\n")
            f.flush()
            with self.assertRaises(ConfigError) as ctx:
                load_config(Path(f.name))
            self.assertIn(f.name, str(ctx.exception))


class SubmenuConfigTest(unittest.TestCase):
    def assertRefused(self, text, word):
        with self.assertRaises(ConfigError) as ctx:
            parse_config(text)
        self.assertIn(word, str(ctx.exception))

    def test_submenus_switch(self):
        self.assertTrue(parse_config("[menu]\nsubmenus = true\n").submenus)
        self.assertFalse(parse_config("").submenus)

    def test_submenus_must_be_a_boolean(self):
        self.assertRefused("[menu]\nsubmenus = 1\n", "submenus")

    def test_custom_submenus(self):
        cfg = parse_config('[[menu.submenu]]\ntitle = "Tools (rescue)"\nmatch = ["/tools/*"]\n'
                           '[[menu.submenu]]\ntitle = "Old"\nmatch = ["/old/*", "/x/*-2020*"]\n')
        self.assertEqual(cfg.submenu, (Submenu("Tools (rescue)", ("/tools/*",)),
                                       Submenu("Old", ("/old/*", "/x/*-2020*"))))

    def test_submenu_title_reaches_grub_so_it_is_whitelisted(self):
        # A leading "-" would be read by GRUB as an option of `submenu`.
        for title in ('a"b', "a$b", "a\\nb", "a\nb", "", "x" * 61, "a{b", "-x", "--id", "   "):
            with self.subTest(title=title):
                # JSON strings are valid TOML basic strings.
                self.assertRefused(f'[[menu.submenu]]\ntitle = {json.dumps(title)}\nmatch = ["/a"]\n',
                                   "title")

    def test_submenu_needs_a_title_and_patterns(self):
        self.assertRefused('[[menu.submenu]]\nmatch = ["/a"]\n', "title")
        self.assertRefused('[[menu.submenu]]\ntitle = "T"\n', "match")
        self.assertRefused('[[menu.submenu]]\ntitle = "T"\nmatch = ["a"]\n', "match")

    def test_empty_match_is_refused(self):
        # It could never match: a silent no-op is a hidden typo.
        self.assertRefused('[[menu.submenu]]\ntitle = "T"\nmatch = []\n', "match")

    def test_single_table_and_non_tables_are_refused(self):
        self.assertRefused('[menu.submenu]\ntitle = "T"\nmatch = ["/a"]\n', "[[menu.submenu]]")
        self.assertRefused('[menu]\nsubmenu = ["a"]\n', "[[menu.submenu]]")

    def test_unknown_submenu_key_is_refused(self):
        self.assertRefused('[[menu.submenu]]\ntitle = "T"\nmatch = ["/a"]\nclass = "x"\n', "class")

    def test_submenu_must_be_an_array_of_tables(self):
        self.assertRefused('[menu]\nsubmenu = "T"\n', "submenu")


class ExampleTest(unittest.TestCase):
    def test_shipped_example_is_valid_and_uses_submenus(self):
        cfg = load_config(Path(__file__).parent.parent / "examples" / "isolator.toml")
        self.assertTrue(cfg.submenu)


if __name__ == "__main__":
    unittest.main()
