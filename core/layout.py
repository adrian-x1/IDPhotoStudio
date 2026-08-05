"""Physical layout solving without any GUI dependency."""

from dataclasses import dataclass

from PIL import Image, ImageDraw

from core.units import mm_to_px


CUT_LINE_COLOR = (190, 190, 190)
CUT_LINE_WIDTH_MM = 0.3


@dataclass(frozen=True)
class LayoutResult:
    count: int
    columns: int
    rows: int
    photo_rotated: bool
    paper_rotated: bool
    paper_width_mm: float
    paper_height_mm: float


def solve_layout(
    photo_width_mm: float,
    photo_height_mm: float,
    gap: float = 1.0,
    margin: float = 1.0,
    paper: tuple[float, float] = (102, 152),
) -> LayoutResult:
    """Find the highest-capacity grid across photo and paper rotations."""
    candidates: list[LayoutResult] = []

    photo_orientations = (
        (False, photo_width_mm, photo_height_mm),
        (True, photo_height_mm, photo_width_mm),
    )
    paper_orientations = (
        (False, paper[0], paper[1]),
        (True, paper[1], paper[0]),
    )

    for photo_rotated, width_mm, height_mm in photo_orientations:
        for paper_rotated, paper_width_mm, paper_height_mm in paper_orientations:
            columns = int(
                (paper_width_mm - 2 * margin + gap) // (width_mm + gap)
            )
            rows = int(
                (paper_height_mm - 2 * margin + gap) // (height_mm + gap)
            )
            if columns > 0 and rows > 0:
                candidates.append(
                    LayoutResult(
                        count=columns * rows,
                        columns=columns,
                        rows=rows,
                        photo_rotated=photo_rotated,
                        paper_rotated=paper_rotated,
                        paper_width_mm=paper_width_mm,
                        paper_height_mm=paper_height_mm,
                    )
                )

    return max(
        candidates,
        key=lambda result: (
            result.count,
            not result.photo_rotated,
            result.paper_width_mm > result.paper_height_mm,
            result.columns,
        ),
    )


def compose_sheet(
    photo: Image.Image,
    photo_width_mm: float,
    photo_height_mm: float,
    layout: LayoutResult,
    gap: float = 1.0,
    draw_cut_lines: bool = True,
) -> Image.Image:
    """Resize and place one photo across a centered solved 4R grid."""
    canvas = Image.new(
        "RGB",
        (
            mm_to_px(layout.paper_width_mm),
            mm_to_px(layout.paper_height_mm),
        ),
        "white",
    )

    resized_photo = photo.convert("RGB").resize(
        (mm_to_px(photo_width_mm), mm_to_px(photo_height_mm)),
        Image.Resampling.LANCZOS,
    )
    if layout.photo_rotated:
        placed_photo = resized_photo.rotate(90, expand=True)
        placed_width_mm = photo_height_mm
        placed_height_mm = photo_width_mm
    else:
        placed_photo = resized_photo
        placed_width_mm = photo_width_mm
        placed_height_mm = photo_height_mm

    grid_width_mm = (
        layout.columns * placed_width_mm + (layout.columns - 1) * gap
    )
    grid_height_mm = layout.rows * placed_height_mm + (layout.rows - 1) * gap
    start_x_mm = (layout.paper_width_mm - grid_width_mm) / 2
    start_y_mm = (layout.paper_height_mm - grid_height_mm) / 2

    draw = ImageDraw.Draw(canvas)
    line_width = max(1, mm_to_px(CUT_LINE_WIDTH_MM))
    for row in range(layout.rows):
        for column in range(layout.columns):
            x_mm = start_x_mm + column * (placed_width_mm + gap)
            y_mm = start_y_mm + row * (placed_height_mm + gap)
            x = mm_to_px(x_mm)
            y = mm_to_px(y_mm)
            canvas.paste(placed_photo, (x, y))
            if draw_cut_lines:
                draw.rectangle(
                    (
                        x,
                        y,
                        x + placed_photo.width - 1,
                        y + placed_photo.height - 1,
                    ),
                    outline=CUT_LINE_COLOR,
                    width=line_width,
                )

    return canvas
