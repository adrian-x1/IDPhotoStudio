"""Single-window three-pane interface for the stage 2 workflow."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMimeData, QThreadPool, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.crop import (
    CropBox,
    FaceGeometry,
    TargetSize,
    calculate_crop_box,
    is_insufficient_resolution,
)
from core.detect import detect_face
from core.layout import compose_sheet, solve_layout
from core.matting import composite_background
from ui.crop_view import CropView
from ui.matting_worker import MattingWorker
from ui.theme import apply_theme


ORIGINAL_BACKGROUND = "保持原底"
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
        self.setMinimumSize(160, 220)
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
        self.source_image: Image.Image | None = None
        self.face: FaceGeometry | None = None
        self.cropped_original: Image.Image | None = None
        self.finished_photo: Image.Image | None = None
        self.sheet_image: Image.Image | None = None
        self._crop_warning = ""
        self._crop_space_warning = ""
        self._crop_mode_note = ""
        self._crop_revision = 0
        self._foreground_cache: tuple[int, Image.Image] | None = None
        self._active_worker: MattingWorker | None = None
        self._active_matting_revision: int | None = None
        self._pending_matting: tuple[int, Image.Image] | None = None
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)

        application = QApplication.instance()
        if isinstance(application, QApplication):
            apply_theme(application)
        self.setWindowTitle("证件照排版")
        self.setAcceptDrops(True)
        self.setMinimumSize(900, 620)
        self.resize(1200, 760)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        self.app_shell = QWidget(self)
        self.app_shell.setObjectName("appShell")
        self.app_shell.setProperty("dragActive", False)
        root = QVBoxLayout(self.app_shell)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self.header_panel = QWidget()
        self.header_panel.setObjectName("headerPanel")
        header_layout = QHBoxLayout(self.header_panel)
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(10)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        app_title = QLabel("证件照排版")
        app_title.setObjectName("appTitle")
        app_subtitle = QLabel("自动裁剪并排到 6 寸相纸")
        app_subtitle.setObjectName("appSubtitle")
        title_layout.addWidget(app_title)
        title_layout.addWidget(app_subtitle)
        header_layout.addLayout(title_layout)
        header_layout.addStretch(1)

        self.import_actions_container = QWidget()
        import_actions_layout = QHBoxLayout(self.import_actions_container)
        import_actions_layout.setContentsMargins(0, 0, 0, 0)
        import_actions_layout.setSpacing(8)
        self.import_button = QPushButton("导入照片")
        self.import_button.setProperty("variant", "primary")
        self.import_button.setMinimumHeight(38)
        self.import_button.setAccessibleName("导入照片")
        import_actions_layout.addWidget(self.import_button)
        header_layout.addWidget(self.import_actions_container)

        self.output_actions_separator = QFrame()
        self.output_actions_separator.setObjectName("outputSeparator")
        self.output_actions_separator.setFrameShape(QFrame.Shape.VLine)
        self.output_actions_separator.setVisible(False)
        header_layout.addWidget(self.output_actions_separator)

        self.output_actions_container = QWidget()
        self.output_actions_layout = QHBoxLayout(self.output_actions_container)
        self.output_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.output_actions_layout.setSpacing(8)
        self.output_actions_container.setVisible(False)
        header_layout.addWidget(self.output_actions_container)
        root.addWidget(self.header_panel)

        self.crop_view = CropView()
        self.original_preview = self.crop_view
        self.crop_preview = ImagePreview("等待裁剪结果", "裁剪和换底预览")
        self.sheet_preview = ImagePreview("等待生成 6 寸相纸", "相纸排版预览")
        self.crop_preview.setMinimumWidth(280)
        self.sheet_preview.setMinimumWidth(280)

        self.reset_crop_button = QPushButton("重置")
        self.reset_crop_button.setProperty("variant", "quiet")
        self.reset_crop_button.setAccessibleName("重置裁剪框为自动位置")
        self.reset_crop_button.setToolTip("恢复自动裁剪位置")
        self.reset_crop_button.setEnabled(False)

        self.count_label = QLabel(EMPTY_COUNT_TEXT)
        self.count_label.setObjectName("countBadge")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setAccessibleName("排版张数")

        self.original_card = self._preview_panel(
            "原图与裁剪",
            "拖动框或四角调整",
            self.original_preview,
            self.reset_crop_button,
        )
        self.crop_card = self._preview_panel(
            "成片预览",
            "裁剪与换底结果",
            self.crop_preview,
        )
        self.sheet_card = self._preview_panel(
            "6 寸相纸",
            "102 × 152 mm",
            self.sheet_preview,
            self.count_label,
        )

        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(6)
        self.preview_splitter.addWidget(self.original_card)
        self.preview_splitter.addWidget(self.crop_card)
        self.preview_splitter.addWidget(self.sheet_card)
        self.preview_splitter.setStretchFactor(0, 1)
        self.preview_splitter.setStretchFactor(1, 2)
        self.preview_splitter.setStretchFactor(2, 2)
        self.preview_splitter.setSizes([200, 400, 400])
        root.addWidget(self.preview_splitter, 1)

        self.parameters_panel = QFrame()
        self.parameters_panel.setObjectName("parametersPanel")
        self.parameters_panel.setProperty("card", True)
        parameter_rows = QVBoxLayout(self.parameters_panel)
        parameter_rows.setContentsMargins(14, 8, 14, 10)
        parameter_rows.setSpacing(5)

        settings_header = QHBoxLayout()
        settings_header.setContentsMargins(0, 0, 0, 0)
        settings_title = QLabel("输出设置")
        settings_title.setObjectName("sectionTitle")
        settings_header.addWidget(settings_title)
        settings_header.addStretch(1)
        self.reset_spacing_button = QPushButton("恢复默认")
        self.reset_spacing_button.setProperty("variant", "quiet")
        self.reset_spacing_button.setAccessibleName("重置间距和边距为默认值")
        self.reset_spacing_button.setToolTip("间距和边距恢复为 1.0mm")
        settings_header.addWidget(self.reset_spacing_button)
        parameter_rows.addLayout(settings_header)

        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(8)
        first_row.addWidget(self._field_label("规格"))
        self.spec_combo = QComboBox()
        self.spec_combo.setMinimumWidth(148)
        self.spec_combo.addItems(self.specs)
        self.spec_combo.setAccessibleName("证件照规格")
        first_row.addWidget(self.spec_combo)
        first_row.addSpacing(12)
        first_row.addWidget(self._field_label("底色"))
        self.background_group = QButtonGroup(self)
        self.original_background_radio = QRadioButton(ORIGINAL_BACKGROUND)
        self.white_background_radio = QRadioButton("白")
        self.blue_background_radio = QRadioButton("蓝")
        self.red_background_radio = QRadioButton("红")
        for radio in (
            self.original_background_radio,
            self.white_background_radio,
            self.blue_background_radio,
            self.red_background_radio,
        ):
            self.background_group.addButton(radio)
            first_row.addWidget(radio)
        self.original_background_radio.setChecked(True)
        first_row.addStretch(1)
        parameter_rows.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setContentsMargins(0, 0, 0, 0)
        second_row.setSpacing(8)
        second_row.addWidget(self._field_label("间距"))
        self.gap_spin = self._millimetre_spinbox("照片间距")
        second_row.addWidget(self.gap_spin)
        second_row.addWidget(self._field_label("mm"))
        second_row.addSpacing(12)
        second_row.addWidget(self._field_label("边距"))
        self.margin_spin = self._millimetre_spinbox("相纸边距")
        second_row.addWidget(self.margin_spin)
        second_row.addWidget(self._field_label("mm"))
        second_row.addSpacing(12)
        self.cut_lines_check = QCheckBox("裁剪线")
        self.cut_lines_check.setChecked(True)
        self.cut_lines_check.setAccessibleName("显示裁剪线")
        second_row.addWidget(self.cut_lines_check)
        second_row.addStretch(1)
        parameter_rows.addLayout(second_row)
        root.addWidget(self.parameters_panel)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        self.warning_label.setAccessibleName("换底提示")
        root.addWidget(self.warning_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAccessibleName("抠图进度")
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("请先导入一张照片")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("处理状态")
        root.addWidget(self.status_label)

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
        self.reset_crop_button.clicked.connect(self.crop_view.reset_to_auto)
        self.reset_spacing_button.clicked.connect(self._reset_spacing)
        self.crop_view.cropBoxChanged.connect(self._on_crop_box_changed)
        self.crop_view.interactionFinished.connect(
            self._on_crop_interaction_finished
        )
        self.spec_combo.currentTextChanged.connect(self._on_spec_changed)
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
            self.source_image = None
            self.crop_view.clear_image()
            self.reset_crop_button.setEnabled(False)
            self._clear_processed_previews()
            self._set_matting_progress(False)
            self.status_label.setText(f"无法读取照片：{error}")
            return False

        self.source_image = source
        self.crop_view.set_image(source)
        try:
            face = detect_face(np.asarray(source))
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            self.face = None
            self.reset_crop_button.setEnabled(False)
            self._clear_processed_previews()
            self._set_matting_progress(False)
            self.status_label.setText(f"人脸检测失败：{error}")
            return False

        if face is None:
            self.face = None
            self._refresh_crop()
            return False

        self.face = face
        self._refresh_crop()
        return True

    def _on_spec_changed(self) -> None:
        if self.source_image is not None:
            self._refresh_crop()

    def _refresh_crop(self) -> None:
        if self.source_image is None:
            return
        self._invalidate_crop_revision()
        spec = self.specs[self.spec_combo.currentText()]
        target = TargetSize(spec["width_mm"], spec["height_mm"])
        aspect_ratio = target.width_mm / target.height_mm
        if self.face is not None:
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
            self.reset_crop_button.setEnabled(True)
        else:
            box = self._centered_manual_box(aspect_ratio)
            self._crop_space_warning = ""
            self._crop_mode_note = "未检测到人脸，已进入手动裁剪模式"
            self.reset_crop_button.setEnabled(False)

        self.crop_view.set_content(self.source_image, box, aspect_ratio)
        self._set_cropped_original(box)
        self._update_crop_warning(box, target)
        self._apply_background_selection()

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
        self.cropped_original = self.source_image.crop(
            (round(box.left), round(box.top), round(box.right), round(box.bottom))
        )

    def _update_crop_warning(
        self,
        box: CropBox,
        target: TargetSize,
    ) -> None:
        warnings = [self._crop_space_warning] if self._crop_space_warning else []
        if is_insufficient_resolution(box, target):
            warnings.append("裁剪区域像素不足，放大后可能模糊")
        self._crop_warning = "；".join(warnings)

    def _on_crop_box_changed(self, box: CropBox) -> None:
        if self.source_image is None:
            return
        self._invalidate_crop_revision()
        target = self._current_target_size()
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

    def _current_target_size(self) -> TargetSize:
        spec = self.specs[self.spec_combo.currentText()]
        return TargetSize(spec["width_mm"], spec["height_mm"])

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
            self.warning_label.setText(
                "白底照片换蓝/红底会在发丝处留白边，建议直接用对应背景色重拍"
            )
            self.warning_label.setVisible(True)
        elif background == "白":
            self.warning_label.setText("换底是实验功能，效果取决于原图背景。")
            self.warning_label.setVisible(True)
        else:
            self.warning_label.clear()
            self.warning_label.setVisible(False)

    def _apply_background_selection(self) -> None:
        if self.cropped_original is None:
            return
        background = self._selected_background()
        self._update_background_warning()
        if background == ORIGINAL_BACKGROUND:
            self._pending_matting = None
            self.finished_photo = self.cropped_original
            self.crop_preview.set_image(self.finished_photo)
            self._refresh_layout()
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
            self._refresh_layout()
            self._set_matting_progress(False)
            self._set_status("换底完成")
            return

        self.finished_photo = self.cropped_original
        self.crop_preview.set_image(self.finished_photo)
        self._refresh_layout()
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

    def _refresh_layout(
        self,
        *,
        resample: Image.Resampling = Image.Resampling.LANCZOS,
    ) -> None:
        if self.finished_photo is None:
            return
        spec = self.specs[self.spec_combo.currentText()]
        gap = self.gap_spin.value()
        margin = self.margin_spin.value()
        try:
            layout = solve_layout(
                spec["width_mm"],
                spec["height_mm"],
                gap=gap,
                margin=margin,
            )
        except ValueError:
            self.sheet_image = None
            self.sheet_preview.clear_image("当前参数无法排入相纸")
            self.count_label.setText("共 0 张")
            return

        self.sheet_image = compose_sheet(
            self.finished_photo,
            spec["width_mm"],
            spec["height_mm"],
            layout,
            gap=gap,
            draw_cut_lines=self.cut_lines_check.isChecked(),
            resample=resample,
        )
        self.sheet_preview.set_image(self.sheet_image)
        self.count_label.setText(f"共 {layout.count} 张")

    def _clear_processed_previews(self) -> None:
        self.face = None
        self.cropped_original = None
        self.finished_photo = None
        self.sheet_image = None
        self.crop_preview.clear_image("等待自动裁剪")
        self.sheet_preview.clear_image("等待生成相纸排版")
        self.count_label.setText(EMPTY_COUNT_TEXT)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._invalidate_crop_revision()
        self._thread_pool.clear()
        super().closeEvent(event)
