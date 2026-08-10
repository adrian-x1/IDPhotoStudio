"""Single-window three-pane interface for the stage 2 workflow."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QEvent, QMimeData, QSize, QThreadPool, QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFocusEvent,
    QIcon,
    QPixmap,
    QResizeEvent,
    QValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.crop import (
    CropBox,
    FaceGeometry,
    TargetSize,
    calculate_crop_box,
    integer_crop_bounds,
    is_insufficient_resolution,
    minimum_face_height_for_300dpi,
)
from core.detect import detect_face
from core.export import export_jpeg, export_pdf, export_png, render_photo
from core.layout import (
    CUSTOM_SIZE_MAX_MM,
    CUSTOM_SIZE_MIN_MM,
    LayoutResult,
    LayoutTooLargeError,
    compose_sheet,
    solve_layout,
)
from core.matting import composite_background
from ui.crop_view import CropView
from ui.matting_worker import MattingWorker
from ui.printing import PrintOutcome, print_sheet
from ui.theme import CONTROL_ICON_PATHS, apply_theme


ORIGINAL_BACKGROUND = "保持原底"
CUSTOM_SPEC_LABEL = "自定义"
CUSTOM_SIZE_PLACEHOLDER = "--"
# Wide enough that the widget never rejects a keystroke on its own; the real
# bounds live in core.layout and are enforced when the value is committed.
CUSTOM_SIZE_ENTRY_MAX_MM = 9999.0
EMPTY_COUNT_TEXT = "共 — 张"
DEFAULT_SPACING_MM = 1.0
SUPPORTED_IMAGE_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
)
IMAGE_FILE_FILTER = "照片 (" + " ".join(
    f"*{suffix}" for suffix in SUPPORTED_IMAGE_SUFFIXES
) + ")"
JPEG_FILE_FILTER = "JPEG 图像 (*.jpg *.jpeg)"
PNG_FILE_FILTER = "PNG 图像 (*.png)"
PDF_FILE_FILTER = "PDF 文档 (*.pdf)"


def _rotate_image_clockwise(
    image: Image.Image,
    quarter_turns: int,
) -> Image.Image:
    turns = quarter_turns % 4
    if turns == 1:
        return image.transpose(Image.Transpose.ROTATE_270)
    if turns == 2:
        return image.transpose(Image.Transpose.ROTATE_180)
    if turns == 3:
        return image.transpose(Image.Transpose.ROTATE_90)
    return image


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[1]


def _load_specs() -> dict[str, dict[str, int]]:
    path = _resource_root() / "specs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _first_supported_local_image(mime_data: QMimeData) -> Path | None:
    if not mime_data.hasUrls():
        return None
    urls = mime_data.urls()
    if not urls or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return None
    return path


class ImagePreview(QLabel):
    """A label that keeps one source pixmap fitted without distortion."""

    def __init__(self, empty_text: str, accessible_name: str) -> None:
        super().__init__(empty_text)
        self._empty_text = empty_text
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(120, 100)
        self.setObjectName("previewCanvas")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName(accessible_name)
        self.setWordWrap(True)
        self.setPixmap(QPixmap())
        self.setText(empty_text)

    def set_image(self, image: Image.Image) -> None:
        qimage = ImageQt(image.convert("RGBA"))
        self._source_pixmap = QPixmap.fromImage(qimage.copy())
        self.setText("")
        self._fit_pixmap()

    def clear_image(self, message: str | None = None) -> None:
        self._source_pixmap = None
        self.setPixmap(QPixmap())
        self.setText(message or self._empty_text)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_pixmap()

    def _fit_pixmap(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        available = self.contentsRect().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(
            self._source_pixmap.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CustomSizeSpinBox(QDoubleSpinBox):
    """Millimetre entry whose empty text means "not filled in yet".

    A plain ``QDoubleSpinBox`` policed the custom bounds through its own range,
    which made the widget swallow keystrokes instead of reporting a mistake:
    typing 200 into a 0-152 box left 20 behind and committed it as valid.  The
    range here stays wide open so ``_commit_custom_dimension`` is the only place
    that decides what is acceptable, and blank text round-trips to 0 so the
    field can be cleared back to the unfilled state.
    """

    def __init__(self, accessible_name: str) -> None:
        super().__init__()
        self.setRange(0.0, CUSTOM_SIZE_ENTRY_MAX_MM)
        self.setDecimals(1)
        self.setSingleStep(1.0)
        self.setKeyboardTracking(False)
        self.setAccessibleName(accessible_name)
        self.setProperty("invalid", False)
        self._select_all_pending = False
        self.lineEdit().setPlaceholderText(CUSTOM_SIZE_PLACEHOLDER)
        self.lineEdit().installEventFilter(self)
        self.lineEdit().setText("")

    def validate(self, text: str, position: int) -> object:
        if not text.strip():
            return (QValidator.State.Acceptable, text, position)
        return super().validate(text, position)

    def valueFromText(self, text: str) -> float:
        if not text.strip():
            return 0.0
        return super().valueFromText(text)

    def textFromValue(self, value: float) -> str:
        if value == 0.0:
            return ""
        return super().textFromValue(value)

    def stepBy(self, steps: int) -> None:
        """Keep the arrows inside the valid band so they never produce an error."""
        if self.value() == 0.0:
            if steps > 0:
                self.setValue(CUSTOM_SIZE_MIN_MM)
            return
        super().stepBy(steps)
        self.setValue(
            min(max(self.value(), CUSTOM_SIZE_MIN_MM), CUSTOM_SIZE_MAX_MM)
        )

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        # Qt only selects all on tab focus, so arriving by click would drop the
        # caret mid-text and the next keystroke would extend the old number
        # instead of replacing it.  Offer the whole number on that first click
        # only: clicking again inside a field that already has focus means the
        # user is aiming at one digit, so the caret must land where they aimed.
        self._select_all_pending = True

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:
        if (
            self._select_all_pending
            and watched is self.lineEdit()
            and event.type() == QEvent.Type.MouseButtonRelease
        ):
            self._select_all_pending = False
            # A drag that lands here already carries the user's own selection.
            if not self.lineEdit().hasSelectedText():
                self.selectAll()
        return super().eventFilter(watched, event)


class MainWindow(QMainWindow):
    """Coordinate import, automatic crop, and live 4R sheet preview."""

    def mousePressEvent(self, event) -> None:
        """Clicking empty space drops spinbox focus so its edit ring clears."""
        self._clear_parameter_focus()
        super().mousePressEvent(event)

    def _clear_parameter_focus(self) -> None:
        focused = QApplication.focusWidget()
        if isinstance(focused, QDoubleSpinBox):
            focused.clearFocus()

    def __init__(self) -> None:
        super().__init__()
        self.specs = _load_specs()
        assert CUSTOM_SPEC_LABEL not in self.specs
        self._original_source_image: Image.Image | None = None
        self.source_image: Image.Image | None = None
        self.face: FaceGeometry | None = None
        self.face_count = 0
        self._photo_rotation_quarters = 0
        self._crop_orientation_landscape = False
        self.cropped_original: Image.Image | None = None
        self.finished_photo: Image.Image | None = None
        self.sheet_image: Image.Image | None = None
        self.sheet_layout: LayoutResult | None = None
        self._crop_warning = ""
        self._crop_space_warning = ""
        self._crop_mode_note = ""
        self._input_warnings: list[str] = []
        self._custom_width_mm: float | None = None
        self._custom_height_mm: float | None = None
        self._custom_width_error = ""
        self._custom_height_error = ""
        self._custom_size_error = ""
        self._layout_error = ""
        self._background_note = ""
        self._crop_revision = 0
        self._foreground_cache: tuple[int, Image.Image] | None = None
        self._active_worker: MattingWorker | None = None
        self._active_matting_revision: int | None = None
        self._pending_matting: tuple[int, Image.Image] | None = None
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._sheet_preview_is_fast = False
        self._layout_refine_timer = QTimer(self)
        self._layout_refine_timer.setSingleShot(True)
        self._layout_refine_timer.setInterval(250)
        self._layout_refine_timer.timeout.connect(self._refine_layout_preview)

        application = QApplication.instance()
        if isinstance(application, QApplication):
            apply_theme(application)
        self.setWindowTitle("证件照排版")
        self.setAcceptDrops(True)
        self.setMinimumSize(1040, 680)
        self.resize(1200, 760)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        self.app_shell = QWidget(self)
        self.app_shell.setObjectName("appShell")
        self.app_shell.setProperty("dragActive", False)
        root = QVBoxLayout(self.app_shell)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        self.header_panel = QWidget()
        self.header_panel.setObjectName("headerPanel")
        self.header_panel.setFixedHeight(56)
        header_layout = QHBoxLayout(self.header_panel)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(8)

        app_title = QLabel("证件照排版")
        app_title.setObjectName("appTitle")
        header_layout.addWidget(app_title)
        header_layout.addStretch(1)

        self.import_button = QPushButton("导入")
        self.import_button.setMinimumHeight(36)
        self.import_button.setAccessibleName("导入照片")
        header_layout.addWidget(
            self.import_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.export_button = QToolButton()
        self.export_button.setText("导出")
        self.export_button.setAccessibleName("导出")
        self.export_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.export_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.export_button.setFixedHeight(36)
        self.export_menu = QMenu(self.export_button)
        photo_section = QAction("单张证件照", self.export_menu)
        photo_section.setEnabled(False)
        photo_section.setSeparator(False)
        self.export_menu.addAction(photo_section)
        self.export_photo_jpeg_action = self.export_menu.addAction("导出 JPEG")
        self.export_photo_png_action = self.export_menu.addAction("导出 PNG")
        sheet_section = QAction("6 寸相纸", self.export_menu)
        sheet_section.setEnabled(False)
        sheet_section.setSeparator(False)
        self.export_menu.addAction(sheet_section)
        self.export_sheet_jpeg_action = self.export_menu.addAction("导出 JPEG")
        self.export_sheet_png_action = self.export_menu.addAction("导出 PNG")
        self.export_sheet_pdf_action = self.export_menu.addAction("导出 PDF")
        self.export_button.setMenu(self.export_menu)

        self.export_button_container: QWidget = self.export_button
        if QApplication.platformName() == "cocoa":
            self.export_button_container = QWidget()
            self.export_button_container.setFixedHeight(40)
            export_button_layout = QHBoxLayout(self.export_button_container)
            export_button_layout.setContentsMargins(0, 4, 0, 0)
            export_button_layout.setSpacing(0)
            export_button_layout.addWidget(self.export_button)
        header_layout.addWidget(
            self.export_button_container, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.header_separator = QFrame()
        self.header_separator.setObjectName("outputSeparator")
        self.header_separator.setFrameShape(QFrame.Shape.VLine)
        self.header_separator.setContentsMargins(4, 0, 4, 0)
        header_layout.addWidget(self.header_separator)

        self.print_button = QPushButton("打印")
        self.print_button.setAccessibleName("打印")
        self.print_button.setProperty("variant", "primary")
        self.print_button.setMinimumHeight(36)
        header_layout.addWidget(
            self.print_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self._refresh_output_actions_enabled()
        root.addWidget(self.header_panel)

        self.parameters_panel = QFrame()
        self.parameters_panel.setObjectName("parametersPanel")
        self.parameters_panel.setProperty("card", True)
        self.parameters_panel.setFixedWidth(220)
        parameter_rows = QVBoxLayout(self.parameters_panel)
        parameter_rows.setContentsMargins(12, 14, 12, 14)
        parameter_rows.setSpacing(8)

        settings_title = QLabel("输出设置")
        settings_title.setObjectName("sectionTitle")
        parameter_rows.addWidget(settings_title)
        parameter_rows.addSpacing(4)

        parameter_rows.addWidget(self._field_label("规格"))
        self.spec_combo = QComboBox()
        self.spec_combo.addItems(self.specs)
        self.spec_combo.addItem(CUSTOM_SPEC_LABEL)
        self.spec_combo.setAccessibleName("证件照规格")
        parameter_rows.addWidget(self.spec_combo)
        parameter_rows.addSpacing(4)

        self.custom_size_row = QWidget()
        self.custom_size_row.setAccessibleName("自定义证件照尺寸")
        custom_size_layout = QVBoxLayout(self.custom_size_row)
        custom_size_layout.setContentsMargins(0, 0, 0, 0)
        custom_size_layout.setSpacing(3)

        custom_width_row = QHBoxLayout()
        custom_width_row.setContentsMargins(0, 0, 0, 0)
        custom_width_row.setSpacing(8)
        custom_width_row.addWidget(self._field_label("宽"))
        self.custom_width_spin = CustomSizeSpinBox("自定义宽度")
        custom_width_row.addWidget(self.custom_width_spin, 1)
        custom_width_row.addWidget(self._field_label("mm"))
        custom_size_layout.addLayout(custom_width_row)

        self.custom_size_separator = QLabel("×")
        self.custom_size_separator.setAccessibleName("宽高分隔符")
        self.custom_size_separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        custom_size_layout.addWidget(self.custom_size_separator)

        custom_height_row = QHBoxLayout()
        custom_height_row.setContentsMargins(0, 0, 0, 0)
        custom_height_row.setSpacing(8)
        custom_height_row.addWidget(self._field_label("高"))
        self.custom_height_spin = CustomSizeSpinBox("自定义高度")
        custom_height_row.addWidget(self.custom_height_spin, 1)
        custom_height_row.addWidget(self._field_label("mm"))
        custom_size_layout.addLayout(custom_height_row)
        self.custom_size_row.setVisible(False)
        parameter_rows.addWidget(self.custom_size_row)
        parameter_rows.addSpacing(4)

        parameter_rows.addWidget(self._field_label("底色"))
        self.background_group = QButtonGroup(self)
        self.original_background_radio = QRadioButton("原底")
        self.original_background_radio.setAccessibleName(ORIGINAL_BACKGROUND)
        self.white_background_radio = QRadioButton("")
        self.white_background_radio.setAccessibleName("白底")
        self.blue_background_radio = QRadioButton("")
        self.blue_background_radio.setAccessibleName("蓝底")
        self.red_background_radio = QRadioButton("")
        self.red_background_radio.setAccessibleName("红底")
        background_radios = (
            (self.original_background_radio, "backgroundOriginal"),
            (self.white_background_radio, "backgroundWhite"),
            (self.blue_background_radio, "backgroundBlue"),
            (self.red_background_radio, "backgroundRed"),
        )
        for radio, object_name in background_radios:
            radio.setObjectName(object_name)
            radio.setProperty("segment", True)
            radio.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            self.background_group.addButton(radio)
        self.original_background_radio.setChecked(True)

        self.background_selector = QWidget()
        self.background_selector.setObjectName("backgroundSelector")
        background_layout = QHBoxLayout(self.background_selector)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(0)
        for radio, _ in background_radios:
            background_layout.addWidget(radio, 1)
        parameter_rows.addWidget(self.background_selector)
        parameter_rows.addSpacing(4)

        parameter_rows.addWidget(self._field_label("间距"))
        gap_row = QHBoxLayout()
        gap_row.setContentsMargins(0, 0, 0, 0)
        gap_row.setSpacing(8)
        self.gap_spin = self._millimetre_spinbox("照片间距")
        gap_row.addWidget(self.gap_spin, 1)
        gap_row.addWidget(self._field_label("mm"))
        parameter_rows.addLayout(gap_row)
        parameter_rows.addSpacing(4)

        parameter_rows.addWidget(self._field_label("边距"))
        margin_row = QHBoxLayout()
        margin_row.setContentsMargins(0, 0, 0, 0)
        margin_row.setSpacing(8)
        self.margin_spin = self._millimetre_spinbox("相纸边距")
        margin_row.addWidget(self.margin_spin, 1)
        margin_row.addWidget(self._field_label("mm"))
        parameter_rows.addLayout(margin_row)
        parameter_rows.addSpacing(4)

        self.cut_lines_check = QCheckBox("裁剪线")
        self.cut_lines_check.setChecked(True)
        self.cut_lines_check.setAccessibleName("显示裁剪线")
        parameter_rows.addWidget(self.cut_lines_check)
        parameter_rows.addStretch(1)

        self.reset_spacing_button = QPushButton("恢复默认")
        self.reset_spacing_button.setProperty("variant", "quiet")
        self.reset_spacing_button.setAccessibleName("重置间距和边距为默认值")
        self.reset_spacing_button.setToolTip("间距和边距恢复为 1.0mm")
        parameter_rows.addWidget(self.reset_spacing_button)

        self.crop_view = CropView()
        self.original_preview = self.crop_view
        self.crop_preview = ImagePreview("等待裁剪结果", "裁剪和换底预览")
        self.sheet_preview = ImagePreview("等待生成 6 寸相纸", "相纸排版预览")
        self.sheet_preview.setObjectName("paperPreview")
        paper_shadow = QGraphicsDropShadowEffect(self.sheet_preview)
        paper_shadow.setBlurRadius(18)
        paper_shadow.setOffset(0, 3)
        paper_shadow.setColor(QColor(0, 0, 0, 115))
        self.sheet_preview.setGraphicsEffect(paper_shadow)

        self.reset_crop_button = QPushButton("重置")
        self.reset_crop_button.setProperty("variant", "quiet")
        self.reset_crop_button.setAccessibleName(
            "重置照片角度、裁剪方向和 AI 裁剪框"
        )
        self.reset_crop_button.setToolTip("恢复原始照片和 AI 初始裁剪位置")
        self.reset_crop_button.setFixedWidth(44)
        self.reset_crop_button.setEnabled(False)

        self.photo_rotation_control = QFrame()
        self.photo_rotation_control.setProperty("segmentedControl", True)
        self.photo_rotation_control.setAccessibleName("照片旋转")
        self.photo_rotation_control.setFixedWidth(76)
        photo_rotation_layout = QHBoxLayout(self.photo_rotation_control)
        photo_rotation_layout.setContentsMargins(1, 1, 1, 1)
        photo_rotation_layout.setSpacing(0)

        self.rotate_photo_left_button = QPushButton("")
        self.rotate_photo_left_button.setProperty("segmentItem", True)
        self.rotate_photo_left_button.setIcon(
            QIcon(str(CONTROL_ICON_PATHS["rotate_left"]))
        )
        self.rotate_photo_left_button.setIconSize(QSize(16, 16))
        self.rotate_photo_left_button.setAccessibleName(
            "向左旋转照片 90 度"
        )
        self.rotate_photo_left_button.setToolTip(
            "照片向左旋转 90°；裁剪框方向不变，可连续点击"
        )
        # Rotation applies immediately and has no on state.  Keeping focus would
        # leave the segment styled like the selected orientation radio next to it.
        self.rotate_photo_left_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_photo_left_button.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.rotate_photo_left_button.setEnabled(False)

        self.photo_rotation_divider = QFrame()
        self.photo_rotation_divider.setProperty("segmentDivider", True)
        self.photo_rotation_divider.setFrameShape(QFrame.Shape.VLine)
        self.photo_rotation_divider.setFixedWidth(1)

        self.rotate_photo_right_button = QPushButton("")
        self.rotate_photo_right_button.setProperty("segmentItem", True)
        self.rotate_photo_right_button.setIcon(
            QIcon(str(CONTROL_ICON_PATHS["rotate_right"]))
        )
        self.rotate_photo_right_button.setIconSize(QSize(16, 16))
        self.rotate_photo_right_button.setAccessibleName(
            "向右旋转照片 90 度"
        )
        self.rotate_photo_right_button.setToolTip(
            "照片向右旋转 90°；裁剪框方向不变，可连续点击"
        )
        self.rotate_photo_right_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_photo_right_button.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.rotate_photo_right_button.setEnabled(False)
        photo_rotation_layout.addWidget(self.rotate_photo_left_button)
        photo_rotation_layout.addWidget(self.photo_rotation_divider)
        photo_rotation_layout.addWidget(self.rotate_photo_right_button)

        self.crop_orientation_control = QFrame()
        self.crop_orientation_control.setProperty("segmentedControl", True)
        self.crop_orientation_control.setAccessibleName("裁剪框方向")
        self.crop_orientation_control.setFixedWidth(106)
        self.crop_orientation_control.setEnabled(False)
        crop_orientation_layout = QHBoxLayout(self.crop_orientation_control)
        crop_orientation_layout.setContentsMargins(1, 1, 1, 1)
        crop_orientation_layout.setSpacing(0)

        self.crop_orientation_group = QButtonGroup(self)
        self.portrait_crop_radio = QRadioButton("竖版")
        self.portrait_crop_radio.setProperty("segmentItem", True)
        self.portrait_crop_radio.setAccessibleName("竖版裁剪框")
        self.portrait_crop_radio.setToolTip(
            "使用竖版裁剪框；照片方向不变，不改变 6 寸相纸排版"
        )
        self.portrait_crop_radio.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.portrait_crop_radio.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.portrait_crop_radio.setEnabled(False)

        self.crop_orientation_divider = QFrame()
        self.crop_orientation_divider.setProperty("segmentDivider", True)
        self.crop_orientation_divider.setFrameShape(QFrame.Shape.VLine)
        self.crop_orientation_divider.setFixedWidth(1)

        self.landscape_crop_radio = QRadioButton("横版")
        self.landscape_crop_radio.setProperty("segmentItem", True)
        self.landscape_crop_radio.setAccessibleName("横版裁剪框")
        self.landscape_crop_radio.setToolTip(
            "使用横版裁剪框；照片方向不变，不改变 6 寸相纸排版"
        )
        self.landscape_crop_radio.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.landscape_crop_radio.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.landscape_crop_radio.setEnabled(False)
        for radio in (self.portrait_crop_radio, self.landscape_crop_radio):
            self.crop_orientation_group.addButton(radio)
        self.portrait_crop_radio.setChecked(True)
        crop_orientation_layout.addWidget(self.portrait_crop_radio)
        crop_orientation_layout.addWidget(self.crop_orientation_divider)
        crop_orientation_layout.addWidget(self.landscape_crop_radio)

        crop_header_actions = QWidget()
        crop_header_layout = QHBoxLayout(crop_header_actions)
        crop_header_layout.setContentsMargins(0, 0, 0, 0)
        crop_header_layout.setSpacing(6)
        crop_header_layout.addWidget(self.photo_rotation_control)
        crop_header_layout.addWidget(self.crop_orientation_control)
        crop_header_layout.addWidget(self.reset_crop_button)

        self.count_label = QLabel(EMPTY_COUNT_TEXT)
        self.count_label.setObjectName("countBadge")
        self.count_label.setAccessibleName("排版张数")
        self.count_label.setVisible(False)
        self.count_number_label = QLabel("—")
        self.count_number_label.setObjectName("countNumber")
        self.count_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_number_label.setAccessibleName("排版张数数字")
        self.count_unit_label = QLabel("张")
        self.count_unit_label.setObjectName("countUnit")
        self.count_unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_display = QWidget()
        count_display.setObjectName("countDisplay")
        count_display.setFixedWidth(76)
        count_layout = QVBoxLayout(count_display)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.setSpacing(0)
        count_layout.addStretch(1)
        count_layout.addWidget(self.count_number_label)
        count_layout.addWidget(self.count_unit_label)
        count_layout.addStretch(1)
        count_layout.addWidget(self.count_label)

        sheet_content = QWidget()
        sheet_content.setObjectName("sheetContent")
        sheet_layout = QHBoxLayout(sheet_content)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.setSpacing(12)
        sheet_layout.addWidget(self.sheet_preview, 1)
        sheet_layout.addWidget(count_display)

        self.original_card = self._preview_panel(
            "裁剪区域",
            "拖动、滚轮或方向键微调",
            self.original_preview,
            crop_header_actions,
        )
        self.crop_card = self._preview_panel(
            "成品单张",
            "裁剪与换底结果",
            self.crop_preview,
        )
        self.sheet_card = self._preview_panel(
            "6 寸相纸",
            "102 × 152 mm",
            sheet_content,
        )

        self.right_column = QWidget()
        self.right_column.setObjectName("rightColumn")
        right_layout = QVBoxLayout(self.right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.crop_card, 1)
        right_layout.addWidget(self.sheet_card, 1)

        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(8)
        self.preview_splitter.addWidget(self.parameters_panel)
        self.preview_splitter.addWidget(self.original_card)
        self.preview_splitter.addWidget(self.right_column)
        self.preview_splitter.setStretchFactor(0, 0)
        self.preview_splitter.setStretchFactor(1, 115)
        self.preview_splitter.setStretchFactor(2, 100)
        self.preview_splitter.setSizes([220, 529, 460])
        root.addWidget(self.preview_splitter, 1)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        self.warning_label.setAccessibleName("换底提示")
        self.warning_label.setProperty("severity", "")
        root.addWidget(self.warning_label)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setFixedHeight(28)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(12)

        self.status_label = QLabel("请先导入一张照片")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(False)
        self.status_label.setAccessibleName("处理状态")
        status_layout.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setAccessibleName("抠图进度")
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)
        root.addWidget(self.status_bar)

        self.setCentralWidget(self.app_shell)

    @staticmethod
    def _preview_panel(
        title: str,
        subtitle: str,
        preview: QWidget,
        header_widget: QWidget | None = None,
    ) -> QFrame:
        panel = QFrame()
        panel.setProperty("card", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        description = QLabel(subtitle)
        description.setObjectName("cardSubtitle")
        title_layout.addWidget(heading)
        title_layout.addWidget(description)
        header.addLayout(title_layout)
        header.addStretch(1)
        if header_widget is not None:
            header.addWidget(header_widget)
        layout.addLayout(header)
        layout.addWidget(preview, 1)
        return panel

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    @staticmethod
    def _millimetre_spinbox(accessible_name: str) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 20.0)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(0.5)
        spinbox.setValue(DEFAULT_SPACING_MM)
        spinbox.setAccessibleName(accessible_name)
        return spinbox

    def _reset_spacing(self) -> None:
        """Restore gap and margin to their defaults, refreshing layout once."""
        self.gap_spin.setValue(DEFAULT_SPACING_MM)
        self.margin_spin.setValue(DEFAULT_SPACING_MM)
        self._clear_parameter_focus()

    def _connect_signals(self) -> None:
        self.import_button.clicked.connect(self._choose_image)
        self.crop_view.emptyStateActivated.connect(self._choose_image)
        self.export_photo_jpeg_action.triggered.connect(
            self._choose_photo_jpeg_destination
        )
        self.export_photo_png_action.triggered.connect(
            self._choose_photo_png_destination
        )
        self.export_sheet_jpeg_action.triggered.connect(
            self._choose_sheet_jpeg_destination
        )
        self.export_sheet_png_action.triggered.connect(
            self._choose_sheet_png_destination
        )
        self.export_sheet_pdf_action.triggered.connect(
            self._choose_sheet_pdf_destination
        )
        self.print_button.clicked.connect(self._print_current_sheet)
        self.reset_crop_button.clicked.connect(self._reset_to_ai_initial)
        self.reset_spacing_button.clicked.connect(self._reset_spacing)
        self.rotate_photo_left_button.clicked.connect(self._rotate_photo_left)
        self.rotate_photo_right_button.clicked.connect(self._rotate_photo_right)
        self.portrait_crop_radio.toggled.connect(
            self._on_crop_orientation_toggled
        )
        self.landscape_crop_radio.toggled.connect(
            self._on_crop_orientation_toggled
        )
        self.crop_view.cropBoxChanged.connect(self._on_crop_box_changed)
        self.crop_view.interactionFinished.connect(
            self._on_crop_interaction_finished
        )
        self.spec_combo.currentTextChanged.connect(self._on_spec_changed)
        self.custom_width_spin.editingFinished.connect(
            self._on_custom_width_committed
        )
        self.custom_height_spin.editingFinished.connect(
            self._on_custom_height_committed
        )
        self.gap_spin.valueChanged.connect(self._refresh_layout)
        self.margin_spin.valueChanged.connect(self._refresh_layout)
        self.cut_lines_check.toggled.connect(self._refresh_layout)
        for radio in (
            self.original_background_radio,
            self.white_background_radio,
            self.blue_background_radio,
            self.red_background_radio,
        ):
            radio.toggled.connect(self._on_background_toggled)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入照片",
            "",
            IMAGE_FILE_FILTER,
        )
        if path:
            self.load_image(path)

    def _choose_photo_jpeg_destination(self) -> None:
        if self.finished_photo is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出单张 JPEG",
            f"{self._export_basename()}.jpg",
            JPEG_FILE_FILTER,
        )
        if not path:
            return
        target = self._current_target_size()
        assert target is not None
        photo = render_photo(
            self.finished_photo,
            target.width_mm,
            target.height_mm,
        )
        try:
            export_jpeg(photo, path)
        except (IOError, PermissionError) as error:
            self.status_label.setText(f"导出单张 JPEG 失败：{error}")
            return
        self.status_label.setText(f"单张 JPEG 已导出：{path}")

    def _choose_photo_png_destination(self) -> None:
        if self.finished_photo is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出单张 PNG",
            f"{self._export_basename()}.png",
            PNG_FILE_FILTER,
        )
        if not path:
            return
        target = self._current_target_size()
        assert target is not None
        photo = render_photo(
            self.finished_photo,
            target.width_mm,
            target.height_mm,
        )
        try:
            export_png(photo, path)
        except (IOError, PermissionError) as error:
            self.status_label.setText(f"导出单张 PNG 失败：{error}")
            return
        self.status_label.setText(f"单张 PNG 已导出：{path}")

    def _choose_sheet_jpeg_destination(self) -> None:
        if self.sheet_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出相纸 JPEG",
            f"{self._export_basename()}_4R.jpg",
            JPEG_FILE_FILTER,
        )
        if not path:
            return
        self._ensure_full_quality_layout()
        try:
            export_jpeg(self.sheet_image, path)
        except (IOError, PermissionError) as error:
            self.status_label.setText(f"导出相纸 JPEG 失败：{error}")
            return
        self.status_label.setText(f"相纸 JPEG 已导出：{path}")

    def _choose_sheet_png_destination(self) -> None:
        if self.sheet_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出相纸 PNG",
            f"{self._export_basename()}_4R.png",
            PNG_FILE_FILTER,
        )
        if not path:
            return
        self._ensure_full_quality_layout()
        try:
            export_png(self.sheet_image, path)
        except (IOError, PermissionError) as error:
            self.status_label.setText(f"导出相纸 PNG 失败：{error}")
            return
        self.status_label.setText(f"相纸 PNG 已导出：{path}")

    def _choose_sheet_pdf_destination(self) -> None:
        if self.sheet_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出相纸 PDF",
            f"{self._export_basename()}_4R.pdf",
            PDF_FILE_FILTER,
        )
        if not path:
            return
        self._ensure_full_quality_layout()
        try:
            export_pdf(self.sheet_image, path)
        except (IOError, PermissionError) as error:
            self.status_label.setText(f"导出相纸 PDF 失败：{error}")
            return
        self.status_label.setText(f"相纸 PDF 已导出：{path}")

    def _export_basename(self) -> str:
        size = self._spec_size_mm()
        if self._is_custom_spec() and size is not None:
            width_mm, height_mm = size
            return f"{width_mm:g}x{height_mm:g}mm"
        return self.spec_combo.currentText()

    def _print_current_sheet(self) -> None:
        if self.sheet_image is None or self.sheet_layout is None:
            return
        self._ensure_full_quality_layout()
        outcome = print_sheet(self.sheet_image, self.sheet_layout, self)
        if outcome is PrintOutcome.NO_PRINTER:
            self.status_label.setText("没有可用打印机")
        elif outcome is PrintOutcome.PRINTED:
            self.status_label.setText("已发送到打印机")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _first_supported_local_image(event.mimeData()) is not None:
            self._set_drag_active(True)
            event.acceptProposedAction()
        else:
            self._set_drag_active(False)
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        path = _first_supported_local_image(event.mimeData())
        if path is None:
            event.ignore()
            return
        self.load_image(path)
        event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        if self.app_shell.property("dragActive") == active:
            return
        self.app_shell.setProperty("dragActive", active)
        style = self.app_shell.style()
        style.unpolish(self.app_shell)
        style.polish(self.app_shell)
        self.app_shell.update()

    def load_image(self, path: str | Path) -> bool:
        """Load one image and update the three panes; return whether crop succeeded."""
        self._invalidate_crop_revision()
        try:
            with Image.open(path) as opened:
                source = ImageOps.exif_transpose(opened).convert("RGB")
        except (FileNotFoundError, OSError, ValueError) as error:
            self._original_source_image = None
            self.source_image = None
            self._photo_rotation_quarters = 0
            self._crop_orientation_landscape = False
            self.portrait_crop_radio.setChecked(True)
            self.face_count = 0
            self._input_warnings = []
            self.crop_view.clear_image()
            self._set_rotation_controls_enabled(False)
            self.reset_crop_button.setEnabled(False)
            self._clear_processed_previews()
            self._set_matting_progress(False)
            self.status_label.setText(f"无法读取照片：{error}")
            return False

        self._original_source_image = source
        self.source_image = source
        self._photo_rotation_quarters = 0
        self._crop_orientation_landscape = False
        self.portrait_crop_radio.setChecked(True)
        self.face = None
        self.face_count = 0
        self._set_rotation_controls_enabled(True)
        self.crop_view.set_image(source)
        return self._detect_current_face_and_refresh()

    def _set_rotation_controls_enabled(self, enabled: bool) -> None:
        for control in (
            self.rotate_photo_left_button,
            self.rotate_photo_right_button,
        ):
            control.setEnabled(enabled)
        self._refresh_crop_orientation_controls()

    def _refresh_crop_orientation_controls(self) -> None:
        custom = self._is_custom_spec()
        enabled = self.source_image is not None and not custom
        self.crop_orientation_control.setEnabled(enabled)
        for radio in (self.portrait_crop_radio, self.landscape_crop_radio):
            radio.setEnabled(enabled)

        if custom:
            tooltip = "自定义尺寸请直接调整宽高"
            self.crop_orientation_control.setToolTip(tooltip)
            self.portrait_crop_radio.setToolTip(tooltip)
            self.landscape_crop_radio.setToolTip(tooltip)
            return

        self.crop_orientation_control.setToolTip("")
        self.portrait_crop_radio.setToolTip(
            "使用竖版裁剪框；照片方向不变，不改变 6 寸相纸排版"
        )
        self.landscape_crop_radio.setToolTip(
            "使用横版裁剪框；照片方向不变，不改变 6 寸相纸排版"
        )

    def _photo_differs_from_ai_initial(self) -> bool:
        """Report whether resetting would actually change anything."""
        return bool(self._photo_rotation_quarters) or self._crop_orientation_landscape

    def _refresh_reset_availability(self, *, face_detected: bool) -> None:
        """Enable reset whenever there is a change to undo.

        Reset must not depend on face detection alone: rotating a photo
        upside down usually defeats the detector, and tying the button to it
        left the user with no way back to the original orientation.
        """
        self.reset_crop_button.setEnabled(
            face_detected or self._photo_differs_from_ai_initial()
        )

    def _detect_current_face_and_refresh(self) -> bool:
        assert self.source_image is not None
        try:
            detection = detect_face(np.asarray(self.source_image))
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            self.face = None
            self.face_count = 0
            self._input_warnings = []
            self._refresh_reset_availability(face_detected=False)
            self._clear_processed_previews()
            self._set_matting_progress(False)
            self.status_label.setText(f"人脸检测失败：{error}")
            return False

        if detection is None:
            self.face = None
            self.face_count = 0
            self._input_warnings = []
            self._refresh_crop()
            return False

        self.face = detection.geometry
        self.face_count = detection.face_count
        self._refresh_crop()
        return True

    def _on_spec_changed(self) -> None:
        custom = self._is_custom_spec()
        self.custom_size_row.setVisible(custom)
        self._refresh_crop_orientation_controls()
        self._refresh_warning_banner()
        if self.source_image is not None:
            self._refresh_crop(layout_resample=Image.Resampling.BOX)
            self._layout_refine_timer.start()

    def _on_custom_width_committed(self) -> None:
        self._commit_custom_dimension(
            self.custom_width_spin,
            value_attribute="_custom_width_mm",
            error_attribute="_custom_width_error",
            dimension_label="宽度",
        )

    def _on_custom_height_committed(self) -> None:
        self._commit_custom_dimension(
            self.custom_height_spin,
            value_attribute="_custom_height_mm",
            error_attribute="_custom_height_error",
            dimension_label="高度",
        )

    def _commit_custom_dimension(
        self,
        spinbox: QDoubleSpinBox,
        *,
        value_attribute: str,
        error_attribute: str,
        dimension_label: str,
    ) -> None:
        value = spinbox.value()
        error = ""
        committed_value: float | None
        if value == 0.0:
            committed_value = None
        elif CUSTOM_SIZE_MIN_MM <= value <= CUSTOM_SIZE_MAX_MM:
            committed_value = value
        else:
            committed_value = None
            error = (
                f"{dimension_label}需在 {CUSTOM_SIZE_MIN_MM:g} - "
                f"{CUSTOM_SIZE_MAX_MM:g} mm 之间"
            )

        setattr(self, error_attribute, error)
        self._custom_size_error = (
            self._custom_width_error or self._custom_height_error
        )
        self._set_spinbox_invalid(spinbox, bool(error))
        self._refresh_warning_banner()
        if error:
            return

        setattr(self, value_attribute, committed_value)
        if self._is_custom_spec() and self.source_image is not None:
            self._refresh_crop()

    @staticmethod
    def _set_spinbox_invalid(spinbox: QDoubleSpinBox, invalid: bool) -> None:
        if spinbox.property("invalid") == invalid:
            return
        spinbox.setProperty("invalid", invalid)
        style = spinbox.style()
        style.unpolish(spinbox)
        style.polish(spinbox)
        spinbox.update()

    def _rotate_photo_left(self) -> None:
        self._rotate_photo(-1)

    def _rotate_photo_right(self) -> None:
        self._rotate_photo(1)

    def _reset_to_ai_initial(self) -> None:
        if self._original_source_image is None:
            return
        self._invalidate_crop_revision()
        self._photo_rotation_quarters = 0
        self._crop_orientation_landscape = False
        self.portrait_crop_radio.setChecked(True)
        self.source_image = self._original_source_image
        self.crop_view.set_image(self.source_image)
        self._detect_current_face_and_refresh()

    def _rotate_photo(self, quarter_delta: int) -> None:
        if self._original_source_image is None:
            return
        self._invalidate_crop_revision()
        self._photo_rotation_quarters = (
            self._photo_rotation_quarters + quarter_delta
        ) % 4
        self.source_image = _rotate_image_clockwise(
            self._original_source_image,
            self._photo_rotation_quarters,
        )
        self.crop_view.set_image(self.source_image)
        self._detect_current_face_and_refresh()

    def _on_crop_orientation_toggled(self, checked: bool) -> None:
        if not checked or self.source_image is None:
            return
        landscape = self.landscape_crop_radio.isChecked()
        if landscape == self._crop_orientation_landscape:
            return
        self._crop_orientation_landscape = landscape
        self._refresh_crop()

    def _refresh_crop(
        self,
        *,
        layout_resample: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> None:
        if self.source_image is None:
            return
        self._invalidate_crop_revision()
        size = self._spec_size_mm()
        if size is None:
            self.crop_view.set_image(self.source_image)
            self._clear_processed_previews(keep_face=True)
            self._set_matting_progress(False)
            self.reset_crop_button.setEnabled(False)
            self._set_custom_size_incomplete_state()
            return

        target = self._current_target_size()
        assert target is not None
        aspect_ratio = target.width_mm / target.height_mm
        if self.face is not None:
            self._input_warnings = []
            if self.face_count > 1:
                self._input_warnings.append(
                    "检测到多张人脸，已按最大的裁剪"
                )
            if abs(self.face.roll_degrees) > 5.0:
                self._input_warnings.append(
                    f"头部倾斜 {abs(self.face.roll_degrees):.1f} 度，建议重拍"
                )
            if self.face.face_height < minimum_face_height_for_300dpi(target):
                self._input_warnings.append("人脸太小，裁剪后像素不足")
            result = calculate_crop_box(
                self.face,
                self.source_image.width,
                self.source_image.height,
                target,
            )
            box = result.box
            self._crop_space_warning = (
                "原图裁剪空间不足，建议重拍留多点余量"
                if result.insufficient_space
                else ""
            )
            self._crop_mode_note = ""
            self._refresh_reset_availability(face_detected=True)
        else:
            box = self._centered_manual_box(aspect_ratio)
            self._input_warnings = []
            self._crop_space_warning = ""
            self._crop_mode_note = "未检测到人脸，已进入手动裁剪模式"
            self._refresh_reset_availability(face_detected=False)

        self.crop_view.set_content(
            self.source_image,
            box,
            aspect_ratio,
            target_size=target,
        )
        self._set_cropped_original(box)
        self._update_crop_warning(box, target)
        self._apply_background_selection(layout_resample=layout_resample)

    def _centered_manual_box(self, aspect_ratio: float) -> CropBox:
        assert self.source_image is not None
        maximum_width = self.source_image.width * 0.8
        maximum_height = self.source_image.height * 0.8
        width = min(maximum_width, maximum_height * aspect_ratio)
        height = width / aspect_ratio
        left = (self.source_image.width - width) / 2
        top = (self.source_image.height - height) / 2
        return CropBox(left, top, left + width, top + height)

    def _set_cropped_original(self, box: CropBox) -> None:
        assert self.source_image is not None
        target = self._current_target_size()
        assert target is not None
        self.cropped_original = self.source_image.crop(
            integer_crop_bounds(
                box,
                self.source_image.width,
                self.source_image.height,
                target.width_mm / target.height_mm,
            )
        )

    def _update_crop_warning(
        self,
        box: CropBox,
        target: TargetSize,
    ) -> None:
        warnings = list(self._input_warnings)
        if self._crop_space_warning:
            warnings.append(self._crop_space_warning)
        assert self.source_image is not None
        left, top, right, bottom = integer_crop_bounds(
            box,
            self.source_image.width,
            self.source_image.height,
            target.width_mm / target.height_mm,
        )
        integer_box = CropBox(0, 0, right - left, bottom - top)
        has_small_face_warning = "人脸太小，裁剪后像素不足" in warnings
        if (
            is_insufficient_resolution(integer_box, target)
            and not has_small_face_warning
        ):
            warnings.append("裁剪区域像素不足，放大后可能模糊")
        self._crop_warning = "；".join(warnings)

    def _on_crop_box_changed(self, box: CropBox) -> None:
        if self.source_image is None:
            return
        self._invalidate_crop_revision()
        target = self._current_target_size()
        if target is None:
            return
        self._set_cropped_original(box)
        self._update_crop_warning(box, target)
        self.finished_photo = self.cropped_original
        self.crop_preview.set_image(self.finished_photo)
        self._refresh_layout(resample=Image.Resampling.BOX)
        self._set_matting_progress(False)
        if self._selected_background() == ORIGINAL_BACKGROUND:
            self._set_status("保持原底，未执行抠图")
        else:
            self._set_status("正在调整裁剪框，松开后重新抠图")

    def _on_crop_interaction_finished(self, box: CropBox) -> None:
        del box
        if self.cropped_original is None:
            return
        if self._selected_background() == ORIGINAL_BACKGROUND:
            self._refresh_layout()
            self._set_status("保持原底，未执行抠图")
        else:
            self._request_matting()

    def _is_custom_spec(self) -> bool:
        return self.spec_combo.currentText() == CUSTOM_SPEC_LABEL

    def _spec_size_mm(self) -> tuple[float, float] | None:
        """Return committed millimetres, or None when custom is incomplete."""
        if self._is_custom_spec():
            if self._custom_width_mm is None or self._custom_height_mm is None:
                return None
            return self._custom_width_mm, self._custom_height_mm

        spec = self.specs.get(self.spec_combo.currentText())
        assert spec is not None
        return float(spec["width_mm"]), float(spec["height_mm"])

    def _current_target_size(self) -> TargetSize | None:
        target = self._standard_target_size()
        if target is None:
            return None
        width_mm = target.width_mm
        height_mm = target.height_mm
        if self._crop_orientation_landscape and not self._is_custom_spec():
            width_mm, height_mm = height_mm, width_mm
        return TargetSize(width_mm, height_mm)

    def _standard_target_size(self) -> TargetSize | None:
        size = self._spec_size_mm()
        if size is None:
            return None
        return TargetSize(*size)

    def _set_custom_size_incomplete_state(self) -> None:
        self._crop_warning = ""
        self._crop_space_warning = ""
        self._crop_mode_note = ""
        self._input_warnings = []
        self._layout_error = ""
        self._refresh_warning_banner()
        self.status_label.setText("请填写自定义宽高")

    def _on_background_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._update_background_warning()
        if self.cropped_original is not None:
            self._apply_background_selection()

    def _selected_background(self) -> str:
        if self.white_background_radio.isChecked():
            return "白"
        if self.blue_background_radio.isChecked():
            return "蓝"
        if self.red_background_radio.isChecked():
            return "红"
        return ORIGINAL_BACKGROUND

    def _update_background_warning(self) -> None:
        background = self._selected_background()
        if background in {"蓝", "红"}:
            self._background_note = (
                "白底照片换蓝/红底会在发丝处留白边，建议直接用对应背景色重拍"
            )
        elif background == "白":
            self._background_note = "换底是实验功能，效果取决于原图背景。"
        else:
            self._background_note = ""
        self._refresh_warning_banner()

    def _refresh_warning_banner(self) -> None:
        """Render the highest-priority message: size > layout > background."""
        size_error = self._custom_size_error if self._is_custom_spec() else ""
        message = size_error or self._layout_error or self._background_note
        severity = "error" if size_error or self._layout_error else ""
        self.warning_label.setText(message)
        self.warning_label.setVisible(bool(message))
        if self.warning_label.property("severity") == severity:
            return
        self.warning_label.setProperty("severity", severity)
        style = self.warning_label.style()
        style.unpolish(self.warning_label)
        style.polish(self.warning_label)
        self.warning_label.update()

    def _apply_background_selection(
        self,
        *,
        layout_resample: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> None:
        if self.cropped_original is None:
            return
        background = self._selected_background()
        self._update_background_warning()
        if background == ORIGINAL_BACKGROUND:
            self._pending_matting = None
            self.finished_photo = self.cropped_original
            self.crop_preview.set_image(self.finished_photo)
            self._refresh_layout(resample=layout_resample)
            self._set_matting_progress(False)
            self._set_status("保持原底，未执行抠图")
            return

        if (
            self._foreground_cache is not None
            and self._foreground_cache[0] == self._crop_revision
        ):
            self.finished_photo = composite_background(
                self._foreground_cache[1],
                background,
            )
            self.crop_preview.set_image(self.finished_photo)
            self._refresh_layout(resample=layout_resample)
            self._set_matting_progress(False)
            self._set_status("换底完成")
            return

        self.finished_photo = self.cropped_original
        self.crop_preview.set_image(self.finished_photo)
        self._refresh_layout(resample=layout_resample)
        self._request_matting()

    def _request_matting(self) -> None:
        if self.cropped_original is None:
            return
        request = (self._crop_revision, self.cropped_original.copy())
        self._set_matting_progress(True)
        self._set_status("正在后台抠图…")
        if self._active_worker is not None:
            if self._active_matting_revision != self._crop_revision:
                self._pending_matting = request
            return
        self._start_matting_worker(*request)

    def _start_matting_worker(self, revision: int, image: Image.Image) -> None:
        worker = MattingWorker(revision, image)
        worker.signals.succeeded.connect(self._on_matting_succeeded)
        worker.signals.failed.connect(self._on_matting_failed)
        self._active_worker = worker
        self._active_matting_revision = revision
        self._thread_pool.start(worker)

    def _on_matting_succeeded(self, revision: int, foreground: Image.Image) -> None:
        self._active_worker = None
        self._active_matting_revision = None
        if revision == self._crop_revision:
            self._foreground_cache = (revision, foreground)
            if (
                self._pending_matting is not None
                and self._pending_matting[0] == revision
            ):
                self._pending_matting = None
            self._apply_background_selection()
        self._start_latest_pending_or_finish()

    def _on_matting_failed(self, revision: int, message: str) -> None:
        self._active_worker = None
        self._active_matting_revision = None
        if revision == self._crop_revision:
            self._pending_matting = None
            if self._selected_background() != ORIGINAL_BACKGROUND:
                self.original_background_radio.setChecked(True)
                self.status_label.setText(
                    f"抠图失败：{message}；已恢复保持原底，可重新选择底色重试"
                )
        self._start_latest_pending_or_finish()

    def _start_latest_pending_or_finish(self) -> None:
        if (
            self._pending_matting is not None
            and self._pending_matting[0] == self._crop_revision
            and self._selected_background() != ORIGINAL_BACKGROUND
            and not (
                self._foreground_cache is not None
                and self._foreground_cache[0] == self._crop_revision
            )
        ):
            revision, image = self._pending_matting
            self._pending_matting = None
            self._start_matting_worker(revision, image)
            return
        self._pending_matting = None
        if self._active_worker is None:
            self._set_matting_progress(False)

    def _invalidate_crop_revision(self) -> None:
        self._layout_refine_timer.stop()
        self._crop_revision += 1
        self._foreground_cache = None
        self._pending_matting = None

    def _set_status(self, message: str) -> None:
        if self._crop_mode_note:
            message = f"{message}；{self._crop_mode_note}"
        if self._crop_warning:
            message = f"{message}；{self._crop_warning}"
        self.status_label.setText(message)

    def _set_matting_progress(self, active: bool) -> None:
        self.progress_bar.setVisible(active)

    def _refine_layout_preview(self) -> None:
        if not self._sheet_preview_is_fast:
            return
        if (
            self._selected_background() != ORIGINAL_BACKGROUND
            and not (
                self._foreground_cache is not None
                and self._foreground_cache[0] == self._crop_revision
            )
        ):
            return
        self._refresh_layout()

    def _ensure_full_quality_layout(self) -> None:
        self._layout_refine_timer.stop()
        if self._sheet_preview_is_fast:
            self._refresh_layout()

    def _refresh_layout(
        self,
        *,
        resample: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> None:
        if self.finished_photo is None:
            return
        size = self._spec_size_mm()
        if size is None:
            return
        width_mm, height_mm = size
        gap = self.gap_spin.value()
        margin = self.margin_spin.value()
        try:
            layout = solve_layout(
                width_mm,
                height_mm,
                gap=gap,
                margin=margin,
            )
        except LayoutTooLargeError as error:
            self._layout_error = str(error)
            self.sheet_image = None
            self.sheet_layout = None
            self._sheet_preview_is_fast = False
            self.sheet_preview.clear_image("当前参数无法排入相纸")
            self._set_count(0)
            self._refresh_output_actions_enabled()
            self._refresh_warning_banner()
            return

        self._layout_error = ""
        self._refresh_warning_banner()
        self.sheet_layout = layout
        layout_photo = self.finished_photo
        if self._crop_orientation_landscape and not self._is_custom_spec():
            layout_photo = layout_photo.transpose(Image.Transpose.ROTATE_270)
        self.sheet_image = compose_sheet(
            layout_photo,
            width_mm,
            height_mm,
            layout,
            gap=gap,
            draw_cut_lines=self.cut_lines_check.isChecked(),
            resample=resample,
        )
        self.sheet_preview.set_image(self.sheet_image)
        self._sheet_preview_is_fast = resample != Image.Resampling.LANCZOS
        self._set_count(layout.count)
        self._refresh_output_actions_enabled()

    def _refresh_output_actions_enabled(self) -> None:
        photo_enabled = self.finished_photo is not None
        sheet_enabled = self.sheet_image is not None
        self.export_photo_jpeg_action.setEnabled(photo_enabled)
        self.export_photo_png_action.setEnabled(photo_enabled)
        self.export_sheet_jpeg_action.setEnabled(sheet_enabled)
        self.export_sheet_png_action.setEnabled(sheet_enabled)
        self.export_sheet_pdf_action.setEnabled(sheet_enabled)
        self.export_button.setEnabled(photo_enabled or sheet_enabled)
        self.print_button.setEnabled(sheet_enabled)

    def _set_count(self, count: int | None) -> None:
        if count is None:
            self.count_label.setText(EMPTY_COUNT_TEXT)
            self.count_number_label.setText("—")
            return
        self.count_label.setText(f"共 {count} 张")
        self.count_number_label.setText(str(count))

    def _clear_processed_previews(self, *, keep_face: bool = False) -> None:
        if not keep_face:
            self.face = None
        self.cropped_original = None
        self.finished_photo = None
        self.sheet_image = None
        self.sheet_layout = None
        self._sheet_preview_is_fast = False
        self._layout_error = ""
        self.crop_preview.clear_image("等待自动裁剪")
        self.sheet_preview.clear_image("等待生成相纸排版")
        self._set_count(None)
        self._refresh_output_actions_enabled()
        self._refresh_warning_banner()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._invalidate_crop_revision()
        self._thread_pool.clear()
        super().closeEvent(event)
