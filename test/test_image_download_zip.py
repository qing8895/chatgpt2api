from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from services.image_service import download_images_zip


class ImageDownloadZipTests(unittest.TestCase):
    def test_zip_preserves_directory_and_includes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "project-a/2026/09/21/task-1_image.png"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_bytes(b"image")
            metadata = [{
                "rel": rel,
                "storage_dir": "project-a",
                "task_id": "task-1",
                "prompt": "cat",
                "model": "gpt-image-2",
                "created_at": "2026-09-21 10:00:00",
                "size": 5,
            }]

            with mock.patch("services.image_service.config", mock.Mock(images_dir=root)), mock.patch(
                "services.image_service.image_storage_service.list_items", return_value=metadata
            ):
                archive = download_images_zip([rel])

            with zipfile.ZipFile(archive) as zf:
                self.assertIn(rel, zf.namelist())
                manifest = json.loads(zf.read("image_manifest.json"))
            self.assertEqual(manifest["images"][0]["task_id"], "task-1")
            self.assertEqual(manifest["images"][0]["prompt"], "cat")


if __name__ == "__main__":
    unittest.main()
