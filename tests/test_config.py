import tempfile
import unittest
from pathlib import Path

from isolator.config import ConfigError, MenuConfig, load_config, parse_config


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


if __name__ == "__main__":
    unittest.main()
