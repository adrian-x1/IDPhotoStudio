"""Physical layout solving without any GUI dependency."""

from dataclasses import dataclass


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
            result.paper_width_mm > result.paper_height_mm,
            not result.photo_rotated,
            result.columns,
        ),
    )
