from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.log_service import LOG_TYPE_CALL, LogService


class LogPaginationTests(unittest.TestCase):
    def test_list_page_reports_total_and_pages_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = LogService(Path(tmp) / "logs.jsonl")
            for index in range(205):
                service.add(LOG_TYPE_CALL, f"call-{index}")

            first = service.list_page(type=LOG_TYPE_CALL, offset=0, limit=100)
            last = service.list_page(type=LOG_TYPE_CALL, offset=200, limit=100)

            self.assertEqual(first["total"], 205)
            self.assertEqual(len(first["items"]), 100)
            self.assertTrue(first["has_more"])
            self.assertEqual(len(last["items"]), 5)
            self.assertFalse(last["has_more"])


if __name__ == "__main__":
    unittest.main()
