import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.windops.core.paths import REPOSITORY_ROOT, resolve_storage_dir


class StoragePathTests(unittest.TestCase):
    def test_default_storage_is_independent_of_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            try:
                os.chdir(temporary)
                self.assertEqual(resolve_storage_dir(), REPOSITORY_ROOT / "storage")
            finally:
                os.chdir(original)

    def test_relative_override_is_repository_relative(self):
        self.assertEqual(resolve_storage_dir("local-data"), REPOSITORY_ROOT / "local-data")

    def test_absolute_override_can_use_external_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(resolve_storage_dir(temporary), Path(temporary).resolve())

    def test_environment_override_is_respected(self):
        with patch.dict(os.environ, {"WINDOPS_STORAGE_DIR": "storage-test"}):
            self.assertEqual(resolve_storage_dir(), REPOSITORY_ROOT / "storage-test")


if __name__ == "__main__":
    unittest.main()
