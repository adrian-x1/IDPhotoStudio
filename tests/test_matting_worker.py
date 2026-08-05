import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from ui.matting_worker import MattingWorker


class MattingWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_emits_foreground_from_thread_pool(self) -> None:
        source = Image.new("RGB", (20, 30), (10, 20, 30))
        foreground = Image.new("RGBA", source.size, (10, 20, 30, 128))
        worker = MattingWorker(7, source)
        succeeded = QSignalSpy(worker.signals.succeeded)
        pool = QThreadPool()
        pool.setMaxThreadCount(1)

        with patch(
            "ui.matting_worker.extract_foreground",
            return_value=foreground,
        ):
            pool.start(worker)
            self.assertTrue(pool.waitForDone(2000))
            self.app.processEvents()

        self.assertEqual(succeeded.count(), 1)
        revision, result = succeeded.at(0)
        self.assertEqual(revision, 7)
        self.assertEqual(result.size, source.size)

    def test_worker_reports_extraction_error(self) -> None:
        worker = MattingWorker(9, Image.new("RGB", (10, 10)))
        failed = QSignalSpy(worker.signals.failed)
        pool = QThreadPool()
        pool.setMaxThreadCount(1)

        with patch(
            "ui.matting_worker.extract_foreground",
            side_effect=RuntimeError("model failed"),
        ):
            pool.start(worker)
            self.assertTrue(pool.waitForDone(2000))
            self.app.processEvents()

        self.assertEqual(failed.count(), 1)
        revision, message = failed.at(0)
        self.assertEqual(revision, 9)
        self.assertIn("model failed", message)


if __name__ == "__main__":
    unittest.main()
