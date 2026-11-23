import unittest

from isolator.profiles import SAFE_ARG, SAFE_CLASS, SAFE_PATH


class WhitelistTest(unittest.TestCase):
    def test_trailing_newline_is_refused(self):
        # With "$", re.match accepts "x\n": a Rock Ridge name or label from an
        # ISO could then add a line break to the GRUB script.
        for regex, value in ((SAFE_PATH, "/a.iso"), (SAFE_ARG, "quiet"), (SAFE_CLASS, "arch")):
            self.assertTrue(regex.match(value))
            self.assertIsNone(regex.match(value + "\n"))


if __name__ == "__main__":
    unittest.main()
