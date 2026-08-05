"""Background rembg execution isolated from the GUI thread."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.matting import extract_foreground


class MattingSignals(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)


class MattingWorker(QRunnable):
    """Extract one foreground and tag the result with its crop revision."""

    def __init__(self, revision: int, image: Image.Image) -> None:
        super().__init__()
        self.revision = revision
        self.image = image.copy()
        self.signals = MattingSignals()

    @Slot()
    def run(self) -> None:
        try:
            foreground = extract_foreground(self.image)
        except Exception as error:  # Worker boundary must report library failures.
            self.signals.failed.emit(self.revision, str(error))
            return
        self.signals.succeeded.emit(self.revision, foreground)
