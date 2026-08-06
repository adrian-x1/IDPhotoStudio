"""Stage 1 command-line acceptance pipeline for a printable ID-photo sheet."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps

from core.crop import TargetSize, calculate_crop_box
from core.detect import detect_face
from core.layout import compose_sheet, solve_layout
from core.matting import BACKGROUND_COLORS, replace_background
from core.units import DPI


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return Path(__file__).resolve().parent


def _load_specs() -> dict[str, dict[str, int]]:
    specs_path = _resource_root() / "specs.json"
    return json.loads(specs_path.read_text(encoding="utf-8"))


def build_sheet(
    input_path: str | Path,
    spec_name: str,
    background: str,
    output_dir: str | Path = "out",
    draw_cut_lines: bool = True,
) -> Path:
    """Run detection, crop, matting, and layout, then save one 300 DPI PNG."""
    specs = _load_specs()
    if spec_name not in specs:
        raise ValueError(f"unknown photo specification: {spec_name}")
    if background not in BACKGROUND_COLORS:
        raise ValueError(f"unknown background: {background}")

    input_path = Path(input_path)
    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    detection = detect_face(np.asarray(image))
    if detection is None:
        raise RuntimeError("未检测到人脸，无法自动裁剪")
    face = detection.geometry

    spec = specs[spec_name]
    target_size = TargetSize(spec["width_mm"], spec["height_mm"])
    crop_result = calculate_crop_box(
        face,
        image.width,
        image.height,
        target_size,
    )
    if crop_result.insufficient_space:
        print("警告：原图裁剪空间不足，建议重拍留多点余量", file=sys.stderr)
    if crop_result.insufficient_resolution:
        print("警告：裁剪区域像素不足，放大后可能模糊", file=sys.stderr)

    box = crop_result.box
    cropped = image.crop(
        (
            round(box.left),
            round(box.top),
            round(box.right),
            round(box.bottom),
        )
    )
    finished_photo = replace_background(cropped, background)
    layout = solve_layout(target_size.width_mm, target_size.height_mm)
    sheet = compose_sheet(
        finished_photo,
        target_size.width_mm,
        target_size.height_mm,
        layout,
        draw_cut_lines=draw_cut_lines,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_{spec_name}_{background}底.png"
    sheet.save(output_path, format="PNG", dpi=(DPI, DPI))
    return output_path


def main(argv: list[str] | None = None) -> int:
    specs = _load_specs()
    parser = argparse.ArgumentParser(description="生成 4R 证件照排版 PNG")
    parser.add_argument("input_path", help="输入人像图片路径")
    parser.add_argument("spec_name", choices=tuple(specs), help="证件照规格")
    parser.add_argument("background", choices=tuple(BACKGROUND_COLORS), help="底色")
    parser.add_argument("--output-dir", default="out", help="输出目录，默认 out/")
    parser.add_argument("--no-cut-lines", action="store_true", help="关闭裁剪参考线")
    args = parser.parse_args(argv)

    try:
        output_path = build_sheet(
            args.input_path,
            args.spec_name,
            args.background,
            output_dir=args.output_dir,
            draw_cut_lines=not args.no_cut_lines,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"错误：{error}\n")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
