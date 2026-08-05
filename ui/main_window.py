"""Single-window three-pane interface for the stage 2 workflow."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.crop import FaceGeometry, TargetSize, calculate_crop_box
from core.detect import detect_face
from core.layout import compose_sheet, solve_layout


ORIGINAL_BACKGROUND = "保持原底"
EMPTY_COUNT_TEXT = "共 — 张"


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[1]


def _load_specs() -> dict[str, dict[str, int]]:
    path = _resource_root() / "specs.json"
    return json.loads(path.read_text(encoding="utf-8"))


class ImagePreview(QLabel):
    """A label that keeps one source pixmap fitted without distortion."""

    def __init__(self, empty_text: str, accessible_name: str) -> None:
        super().__init__(empty_text)
        self._empty_text = empty_text
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(160, 220)
        self.setFrameShape(QFrame.Shape.StyledPanel)
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

    def __init__(self) -> None:
        super().__init__()
        self.specs = _load_specs()
        self.source_image: Image.Image | None = None
        self.face: FaceGeometry | None = None
        self.cropped_original: Image.Image | None = None
        self.finished_photo: Image.Image | None = None
        self.sheet_image: Image.Image | None = None

        self.setWindowTitle("证件照排版")
        self.setMinimumSize(900, 620)
        self.resize(1200, 760)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top_bar = QHBoxLayout()
        self.import_button = QPushButton("导入照片")
        self.import_button.setMinimumHeight(36)
        self.import_button.setAccessibleName("导入照片")
        top_bar.addWidget(self.import_button)
        top_bar.addStretch(1)
        root.addLayout(top_bar)

        self.original_preview = ImagePreview("尚未导入照片", "原图预览")
        self.crop_preview = ImagePreview("等待自动裁剪", "裁剪和换底预览")
        self.sheet_preview = ImagePreview("等待生成相纸排版", "相纸排版预览")

        self.count_label = QLabel(EMPTY_COUNT_TEXT)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_font = self.count_label.font()
        count_font.setBold(True)
        count_font.setPointSize(count_font.pointSize() + 2)
        self.count_label.setFont(count_font)
        self.count_label.setAccessibleName("排版张数")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._preview_panel("原图", self.original_preview))
        splitter.addWidget(self._preview_panel("裁剪 + 换底预览", self.crop_preview))
        splitter.addWidget(
            self._preview_panel("相纸排版预览", self.sheet_preview, self.count_label)
        )
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([240, 480, 480])
        root.addWidget(splitter, 1)

        parameters = QGroupBox("参数")
        parameter_rows = QVBoxLayout(parameters)
        parameter_rows.setSpacing(8)
        first_row = QHBoxLayout()
        second_row = QHBoxLayout()

        first_row.addWidget(QLabel("规格"))
        self.spec_combo = QComboBox()
        self.spec_combo.addItems(self.specs)
        self.spec_combo.setAccessibleName("证件照规格")
        first_row.addWidget(self.spec_combo)

        first_row.addSpacing(16)
        first_row.addWidget(QLabel("底色"))
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

        second_row.addWidget(QLabel("间距"))
        self.gap_spin = self._millimetre_spinbox("照片间距")
        second_row.addWidget(self.gap_spin)
        second_row.addWidget(QLabel("mm"))
        second_row.addSpacing(16)
        second_row.addWidget(QLabel("边距"))
        self.margin_spin = self._millimetre_spinbox("相纸边距")
        second_row.addWidget(self.margin_spin)
        second_row.addWidget(QLabel("mm"))
        second_row.addSpacing(16)
        self.cut_lines_check = QCheckBox("裁剪线")
        self.cut_lines_check.setChecked(True)
        self.cut_lines_check.setAccessibleName("显示裁剪线")
        second_row.addWidget(self.cut_lines_check)
        second_row.addStretch(1)

        parameter_rows.addLayout(first_row)
        parameter_rows.addLayout(second_row)
        root.addWidget(parameters)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        self.warning_label.setAccessibleName("换底提示")
        root.addWidget(self.warning_label)

        self.status_label = QLabel("请先导入一张照片")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("处理状态")
        root.addWidget(self.status_label)

        self.setCentralWidget(central)

    @staticmethod
    def _preview_panel(
        title: str,
        preview: ImagePreview,
        footer: QWidget | None = None,
    ) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        heading = QLabel(title)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        layout.addWidget(preview, 1)
        if footer is not None:
            layout.addWidget(footer)
        return panel

    @staticmethod
    def _millimetre_spinbox(accessible_name: str) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 20.0)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(0.5)
        spinbox.setValue(1.0)
        spinbox.setAccessibleName(accessible_name)
        return spinbox

    def _connect_signals(self) -> None:
        self.import_button.clicked.connect(self._choose_image)
        self.spec_combo.currentTextChanged.connect(self._on_spec_changed)
        self.gap_spin.valueChanged.connect(self._refresh_layout)
        self.margin_spin.valueChanged.connect(self._refresh_layout)
        self.cut_lines_check.toggled.connect(self._refresh_layout)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入照片",
            "",
            "照片 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)",
        )
        if path:
            self.load_image(path)

    def load_image(self, path: str | Path) -> bool:
        """Load one image and update the three panes; return whether crop succeeded."""
        try:
            with Image.open(path) as opened:
                source = ImageOps.exif_transpose(opened).convert("RGB")
        except (FileNotFoundError, OSError, ValueError) as error:
            self._clear_processed_previews()
            self.status_label.setText(f"无法读取照片：{error}")
            return False

        self.source_image = source
        self.original_preview.set_image(source)
        try:
            face = detect_face(np.asarray(source))
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            self.face = None
            self._clear_processed_previews()
            self.status_label.setText(f"人脸检测失败：{error}")
            return False

        if face is None:
            self.face = None
            self._clear_processed_previews()
            self.status_label.setText("未检测到人脸；下一步可使用手动裁剪框")
            return False

        self.face = face
        self._refresh_crop()
        return True

    def _on_spec_changed(self) -> None:
        if self.source_image is not None and self.face is not None:
            self._refresh_crop()

    def _refresh_crop(self) -> None:
        if self.source_image is None or self.face is None:
            return
        spec = self.specs[self.spec_combo.currentText()]
        target = TargetSize(spec["width_mm"], spec["height_mm"])
        result = calculate_crop_box(
            self.face,
            self.source_image.width,
            self.source_image.height,
            target,
        )
        box = result.box
        self.cropped_original = self.source_image.crop(
            (round(box.left), round(box.top), round(box.right), round(box.bottom))
        )
        self.finished_photo = self.cropped_original
        self.crop_preview.set_image(self.finished_photo)
        self._refresh_layout()

        warnings: list[str] = []
        if result.insufficient_space:
            warnings.append("原图裁剪空间不足，建议重拍留多点余量")
        if result.insufficient_resolution:
            warnings.append("裁剪区域像素不足，放大后可能模糊")
        if warnings:
            self.status_label.setText("；".join(warnings))
        else:
            self.status_label.setText("保持原底，未执行抠图")

    def _refresh_layout(self) -> None:
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

