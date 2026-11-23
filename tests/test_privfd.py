import os
import tempfile
import unittest

from isolator.privfd import fd_problem


class FdProblemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile()
        self.addCleanup(self.tmp.close)

    def open(self, flags):
        fd = os.open(self.tmp.name, flags)
        self.addCleanup(os.close, fd)
        return fd

    def test_regular_file_is_refused(self):
        fd = self.open(os.O_RDONLY)
        self.assertIn("block device", fd_problem(fd, (0, 0)))

    def test_writable_descriptor_is_refused(self):
        # Checked before the device type: a writable fd is never acceptable.
        fd = self.open(os.O_RDWR)
        self.assertIn("read-only", fd_problem(fd, (0, 0)))


    def test_other_device_is_refused(self):
        from isolator.privfd import same_device
        self.assertFalse(same_device((8, 0), os.makedev(8, 16)))
        self.assertTrue(same_device((8, 16), os.makedev(8, 16)))


if __name__ == "__main__":
    unittest.main()
