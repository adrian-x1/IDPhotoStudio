"""Interactive fixed-ratio crop overlay rendered over the source image."""

from __future__ import annotations

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QStyle, QStyleOption, QWidget

from core.crop import CropBox
from ui.theme import COLORS


class CropView(QWidget):
    """Show an image with a movable, corner-resizable crop rectangle."""

    cropBoxChanged = Signal(object)
    interactionFinished = Signal(object)

    HANDLE_HIT_RADIUS = 16.0
    HANDLE_VISUAL_RADIUS = 5.0
    MIN_CROP_VIEW_SIZE = 48.0
    EMPTY_TEXT = "拖入照片到窗口任意位置\n或点击右上角导入照片"

    _CORNER_SIGNS = {
        "top_left": (-1, -1),
        "top_right": (1, -1),
        "bottom_right": (1, 1),
        "bottom_left": (-1, 1),
    }

    def __init__(self) -> None:
        super().__init__()
        self._pixmap: QPixmap | None = None
        self._image_width = 0.0
        self._image_height = 0.0
        self._crop_box: CropBox | None = None
        self._automatic_box: CropBox | None = None
        self._aspect_ratio = 1.0
        self._drag_mode: str | None = None
        self._drag_start_point: QPointF | None = None
        self._drag_start_box: CropBox | None = None
        self._drag_changed = False

        self.setMinimumSize(160, 220)
        self.setObjectName("previewCanvas")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("原图裁剪框")

    @property
    def crop_box(self) -> CropBox | None:
        return self._crop_box

    def pixmap(self) -> QPixmap:
        return self._pixmap or QPixmap()

    def set_image(self, image: Image.Image) -> None:
        qimage = ImageQt(image.convert("RGBA"))
        self._pixmap = QPixmap.fromImage(qimage.copy())
        self._image_width = float(image.width)
        self._image_height = float(image.height)
        self._crop_box = None
        self._automatic_box = None
        self._drag_mode = None
        self.update()

    def set_content(
        self,
        image: Image.Image,
        automatic_box: CropBox,
        aspect_ratio: float,
    ) -> None:
        if aspect_ratio <= 0:
            raise ValueError("crop aspect ratio must be positive")
        self.set_image(image)
        self._validate_box(automatic_box)
        self._aspect_ratio = aspect_ratio
        self._automatic_box = automatic_box
        self._crop_box = automatic_box
        self.update()

    def clear_image(self) -> None:
        self._pixmap = None
        self._image_width = 0.0
        self._image_height = 0.0
        self._crop_box = None
        self._automatic_box = None
        self._drag_mode = None
        self.update()

    def reset_to_auto(self) -> None:
        if self._automatic_box is None or self._crop_box == self._automatic_box:
            return
        self._crop_box = self._automatic_box
        self.update()
        self.cropBoxChanged.emit(self._crop_box)
        self.interactionFinished.emit(self._crop_box)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        style_option = QStyleOption()
        style_option.initFrom(self)
        self.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_Widget,
            style_option,
            painter,
            self,
        )
        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self.EMPTY_TEXT,
            )
            return

        image_rect = self._image_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(
            image_rect,
            self._pixmap,
            QRectF(self._pixmap.rect()),
        )
        if self._crop_box is None:
            return

        crop_rect = self._crop_rect_widget()
        shade = QColor(0, 0, 0, 105)
        painter.fillRect(
            QRectF(image_rect.left(), image_rect.top(), image_rect.width(), crop_rect.top() - image_rect.top()),
            shade,
        )
        painter.fillRect(
            QRectF(image_rect.left(), crop_rect.bottom(), image_rect.width(), image_rect.bottom() - crop_rect.bottom()),
            shade,
        )
        painter.fillRect(
            QRectF(image_rect.left(), crop_rect.top(), crop_rect.left() - image_rect.left(), crop_rect.height()),
            shade,
        )
        painter.fillRect(
            QRectF(crop_rect.right(), crop_rect.top(), image_rect.right() - crop_rect.right(), crop_rect.height()),
            shade,
        )

        painter.setPen(QPen(QColor(0, 0, 0, 180), 4))
        painter.drawRect(crop_rect)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(crop_rect)

        handle_color = QColor(COLORS["primary"])
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(handle_color)
        radius = self.HANDLE_VISUAL_RADIUS
        for point in self._handle_points().values():
            painter.drawRect(
                QRectF(
                    point.x() - radius,
                    point.y() - radius,
                    radius * 2,
                    radius * 2,
                )
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._crop_box is None
        ):
            super().mousePressEvent(event)
            return
        mode = self._hit_test(event.position())
        if mode is None:
            super().mousePressEvent(event)
            return
        self._drag_mode = mode
        self._drag_start_point = self._widget_to_image(event.position())
        self._drag_start_box = self._crop_box
        self._drag_changed = False
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode is None:
            self._update_cursor(event.position())
            super().mouseMoveEvent(event)
            return
        self._update_drag(event.position())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._drag_mode is None
        ):
            super().mouseReleaseEvent(event)
            return
        self._update_drag(event.position())
        self.releaseMouse()
        self._drag_mode = None
        self._drag_start_point = None
        self._drag_start_box = None
        self.unsetCursor()
        if self._drag_changed and self._crop_box is not None:
            self.interactionFinished.emit(self._crop_box)
        event.accept()

    def _update_drag(self, widget_point: QPointF) -> None:
        if (
            self._drag_mode is None
            or self._drag_start_point is None
            or self._drag_start_box is None
        ):
            return
        image_point = self._widget_to_image(widget_point)
        if self._drag_mode == "move":
            new_box = self._move_box(image_point)
        else:
            new_box = self._resize_box(image_point)
        if new_box == self._crop_box:
            return
        self._crop_box = new_box
        self._drag_changed = True
        self.update()
        self.cropBoxChanged.emit(new_box)

    def _move_box(self, image_point: QPointF) -> CropBox:
        start = self._drag_start_box
        origin = self._drag_start_point
        assert start is not None and origin is not None
        left = start.left + image_point.x() - origin.x()
        top = start.top + image_point.y() - origin.y()
        left = min(max(left, 0.0), self._image_width - start.width)
        top = min(max(top, 0.0), self._image_height - start.height)
        return CropBox(left, top, left + start.width, top + start.height)

    def _resize_box(self, image_point: QPointF) -> CropBox:
        start = self._drag_start_box
        mode = self._drag_mode
        assert start is not None and mode in self._CORNER_SIGNS
        sign_x, sign_y = self._CORNER_SIGNS[mode]
        anchor_x = start.right if sign_x < 0 else start.left
        anchor_y = start.bottom if sign_y < 0 else start.top

        raw_width = max(0.0, sign_x * (image_point.x() - anchor_x))
        raw_height = max(0.0, sign_y * (image_point.y() - anchor_y))
        desired_width = max(raw_width, raw_height * self._aspect_ratio)

        scale = self._image_scale()
        minimum_width = (
            self.MIN_CROP_VIEW_SIZE / scale * max(1.0, self._aspect_ratio)
        )
        maximum_width_x = anchor_x if sign_x < 0 else self._image_width - anchor_x
        maximum_height = anchor_y if sign_y < 0 else self._image_height - anchor_y
        maximum_width = min(
            maximum_width_x,
            maximum_height * self._aspect_ratio,
        )
        width = min(max(desired_width, minimum_width), maximum_width)
        height = width / self._aspect_ratio

        left = anchor_x - width if sign_x < 0 else anchor_x
        right = anchor_x if sign_x < 0 else anchor_x + width
        top = anchor_y - height if sign_y < 0 else anchor_y
        bottom = anchor_y if sign_y < 0 else anchor_y + height
        return CropBox(left, top, right, bottom)

    def _hit_test(self, widget_point: QPointF) -> str | None:
        radius_squared = self.HANDLE_HIT_RADIUS**2
        for name, handle in self._handle_points().items():
            delta = widget_point - handle
            if delta.x() ** 2 + delta.y() ** 2 <= radius_squared:
                return name
        if self._crop_rect_widget().contains(widget_point):
            return "move"
        return None

    def _update_cursor(self, widget_point: QPointF) -> None:
        mode = self._hit_test(widget_point) if self._crop_box is not None else None
        if mode in {"top_left", "bottom_right"}:
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif mode in {"top_right", "bottom_left"}:
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif mode == "move":
            cursor = Qt.CursorShape.SizeAllCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def _handle_points(self) -> dict[str, QPointF]:
        rect = self._crop_rect_widget()
        return {
            "top_left": rect.topLeft(),
            "top_right": rect.topRight(),
            "bottom_right": rect.bottomRight(),
            "bottom_left": rect.bottomLeft(),
        }

    def _crop_rect_widget(self) -> QRectF:
        if self._crop_box is None:
            return QRectF()
        top_left = self._image_to_widget(
            QPointF(self._crop_box.left, self._crop_box.top)
        )
        bottom_right = self._image_to_widget(
            QPointF(self._crop_box.right, self._crop_box.bottom)
        )
        return QRectF(top_left, bottom_right).normalized()

    def _image_rect(self) -> QRectF:
        if self._image_width <= 0 or self._image_height <= 0:
            return QRectF()
        bounds = self.contentsRect()
        scale = min(
            bounds.width() / self._image_width,
            bounds.height() / self._image_height,
        )
        width = self._image_width * scale
        height = self._image_height * scale
        return QRectF(
            bounds.left() + (bounds.width() - width) / 2,
            bounds.top() + (bounds.height() - height) / 2,
            width,
            height,
        )

    def _image_scale(self) -> float:
        rect = self._image_rect()
        return rect.width() / self._image_width

    def _image_to_widget(self, image_point: QPointF) -> QPointF:
        rect = self._image_rect()
        scale = self._image_scale()
        return QPointF(
            rect.left() + image_point.x() * scale,
            rect.top() + image_point.y() * scale,
        )

    def _widget_to_image(self, widget_point: QPointF) -> QPointF:
        rect = self._image_rect()
        scale = self._image_scale()
        return QPointF(
            (widget_point.x() - rect.left()) / scale,
            (widget_point.y() - rect.top()) / scale,
        )

    def _validate_box(self, box: CropBox) -> None:
        if box.width <= 0 or box.height <= 0:
            raise ValueError("crop box must have positive dimensions")
        if (
            box.left < 0
            or box.top < 0
            or box.right > self._image_width
            or box.bottom > self._image_height
        ):
            raise ValueError("crop box must stay inside the image")
