"""Very sophisticated test which just imports everything.
"""
import unittest
import os
import helper  # noqa
from importlib import import_module


class Test(unittest.TestCase):
    def test_import_all(self):
        for rootp, files, _ in os.walk('src'):
            for f in files:
                if not f.endswith('.py'):
                    continue
                fullpath = os.path.join(rootp, f)
                modpath = fullpath[4:-3].replace(os.path.sep, '.')
                import_module(modpath)


if __name__ == '__main__':
    unittest.main()
