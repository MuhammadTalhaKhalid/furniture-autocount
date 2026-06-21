"""
Furniture Auto Count - core matching engine.

Replicates the CostX "Auto Count" workflow:
    capture a symbol  ->  search the drawing  ->  threshold (tolerance)
    ->  accept/reject  ->  count.

The engine is training-free: it takes ONE captured symbol (template) and finds
every visually similar symbol on a 2D drawing using multi-scale / multi-rotation
normalized template matching, then de-duplicates overlapping hits with NMS.

Author: (freelance CV/ML)  |  PoC for furniture estimation platform.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, asdict

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
#  Data types
# --------------------------------------------------------------------------- #
@dataclass
class Match:
    x: int          # top-left x on the full-res drawing
    y: int          # top-left y
    w: int          # box width
    h: int          # box height
    score: float    # similarity 0..1 (the "%" in the CostX sliders)
    angle: int      # rotation of the template that produced this hit
    accepted: bool = True   # user can toggle in the UI
    manual: bool = False     # True if the user added it by hand

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    def as_dict(self) -> dict:
        d = asdict(self)
        d["center_x"] = self.cx
        d["center_y"] = self.cy
        return d


# --------------------------------------------------------------------------- #
#  PDF / image loading
# --------------------------------------------------------------------------- #
def rasterize_pdf(path: str, dpi: int = 200) -> list[np.ndarray]:
    """Render each PDF page to a BGR image at the given DPI.

    High DPI matters: thin CAD lines disappear at low resolution. 200 is a good
    default for A1/A0 sheets; bump to 300 for dense drawings.
    """
    import fitz  # PyMuPDF

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pages: list[np.ndarray] = []
    with fitz.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8)
            img = img.reshape(pix.height, pix.width, pix.n)
            pages.append(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return pages


def load_image(path: str) -> np.ndarray:
    """Load a raster image (png/jpg/tif) as BGR."""
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# --------------------------------------------------------------------------- #
#  Matching
# --------------------------------------------------------------------------- #
def _rotate(img: np.ndarray, angle: int) -> np.ndarray:
    """Rotate a template by a multiple of 90 deg (cheap, no interpolation loss)."""
    if angle == 0:
        return img
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    # arbitrary angle
    h, w = img.shape[:2]
    c = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(c, angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - c[0]
    M[1, 2] += nh / 2 - c[1]
    return cv2.warpAffine(img, M, (nw, nh), borderValue=255)


def _iou(a: Match, b: Match) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = a.w * a.h + b.w * b.h - inter
    return inter / union


def non_max_suppression(matches: list[Match], iou_thresh: float = 0.3) -> list[Match]:
    """Keep the highest-scoring box in any cluster of overlapping boxes."""
    matches = sorted(matches, key=lambda m: m.score, reverse=True)
    kept: list[Match] = []
    for m in matches:
        if all(_iou(m, k) < iou_thresh for k in kept):
            kept.append(m)
    return kept


def search(
    drawing: np.ndarray,
    template: np.ndarray,
    show_above: float = 0.55,
    scales: tuple[float, ...] = (1.0,),
    angles: tuple[int, ...] = (0,),
    iou_thresh: float = 0.3,
    max_candidates_per_pass: int = 5000,
) -> list[Match]:
    """Find all instances of `template` in `drawing`.

    Parameters mirror the CostX UI:
      show_above   -> "Show matches above %"  (0..1). Lower = more (incl. false +).
      scales       -> handle symbols drawn at slightly different sizes.
      angles       -> handle rotated symbols (e.g. 0/90/180/270).

    Returns NMS-deduplicated matches sorted by score (desc).
    """
    d_gray = to_gray(drawing)
    t_gray0 = to_gray(template)
    H, W = d_gray.shape[:2]

    raw: list[Match] = []
    for angle in angles:
        t_rot = _rotate(t_gray0, angle)
        for s in scales:
            th = max(4, int(round(t_rot.shape[0] * s)))
            tw = max(4, int(round(t_rot.shape[1] * s)))
            if th >= H or tw >= W:
                continue
            t = cv2.resize(t_rot, (tw, th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(d_gray, t, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res >= show_above)
            if len(xs) > max_candidates_per_pass:
                # keep the strongest candidates to bound NMS cost
                order = np.argsort(res[ys, xs])[::-1][:max_candidates_per_pass]
                ys, xs = ys[order], xs[order]
            for x, y in zip(xs, ys):
                raw.append(
                    Match(int(x), int(y), tw, th, float(res[y, x]), int(angle))
                )

    return non_max_suppression(raw, iou_thresh)


# --------------------------------------------------------------------------- #
#  Visualisation
# --------------------------------------------------------------------------- #
def draw_matches(
    drawing: np.ndarray,
    matches: list[Match],
    auto_accept_above: float = 0.7,
) -> np.ndarray:
    """Green = accepted, amber = below auto-accept (needs review), red = rejected."""
    vis = drawing.copy()
    if vis.ndim == 2:
        vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
    for m in matches:
        if not m.accepted:
            color = (0, 0, 255)          # red
        elif m.score >= auto_accept_above:
            color = (0, 170, 0)          # green
        else:
            color = (0, 170, 255)        # amber - review
        cv2.rectangle(vis, (m.x, m.y), (m.x + m.w, m.y + m.h), color, 2)
    return vis


def matches_to_csv(matches: list[Match], item_name: str) -> str:
    import csv

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["item", "index", "center_x", "center_y", "score", "angle", "accepted"])
    for i, m in enumerate(matches, 1):
        w.writerow([item_name, i, m.cx, m.cy, round(m.score, 4), m.angle, m.accepted])
    return buf.getvalue()
