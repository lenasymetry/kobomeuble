"""Symboles DXF: triangles plein/vide (identiques visuellement à l'UI)."""

from __future__ import annotations

import math

from .sanitize import sanitize_layer_name


def _triangle_points(center, size, rotation=0.0):
    cx, cy = float(center[0]), float(center[1])
    s = float(size)
    h = s * math.sqrt(3.0) / 2.0

    # triangle équilatéral pointant vers le haut
    pts = [
        (0.0, 2.0 * h / 3.0),
        (-s / 2.0, -h / 3.0),
        (s / 2.0, -h / 3.0),
    ]

    ang = math.radians(float(rotation))
    cos_a = math.cos(ang)
    sin_a = math.sin(ang)

    out = []
    for x, y in pts:
        xr = x * cos_a - y * sin_a
        yr = x * sin_a + y * cos_a
        out.append((cx + xr, cy + yr))
    return out


def add_filled_triangle(msp_or_layout, center, size, rotation=0, layer="SYMBOLS"):
    """Triangle plein: LWPOLYLINE fermée + HATCH (robuste AutoCAD)."""
    p1, p2, p3 = _triangle_points(center=center, size=size, rotation=rotation)
    pts = [p1, p2, p3]
    # Use close=True for proper polygon
    msp_or_layout.add_lwpolyline(pts, dxfattribs={"layer": sanitize_layer_name(layer, fallback="SYMBOLS")}, close=True)
    try:
        hatch = msp_or_layout.add_hatch(color=256, dxfattribs={"layer": sanitize_layer_name(layer, fallback="SYMBOLS")})
        hatch.paths.add_polyline_path(pts, is_closed=True)
    except Exception:
        pass  # If hatch fails, polyline alone is sufficient
    return (p1, p2, p3)


def add_empty_triangle(msp_or_layout, center, size, rotation=0, layer="SYMBOLS"):
    """Triangle vide: LWPOLYLINE fermée sans hatch."""
    pts = _triangle_points(center=center, size=size, rotation=rotation)
    # Use close=True instead of duplicating first point
    msp_or_layout.add_lwpolyline(pts, dxfattribs={"layer": sanitize_layer_name(layer, fallback="SYMBOLS")}, close=True)
    return tuple(pts)


def add_required_sheet_triangles(
    layout,
    metadata,
    paper_width_mm=420.0,
    margin_mm=10.0,
    base_y_mm=18.0,
    size_mm=8.0,
    rotation_deg=0.0,
):
    """Ajoute les triangles obligatoires (plein + vide) sur chaque layout.

    Position exacte possible via metadata:
      - triangle_filled_center: (x, y)
      - triangle_empty_center: (x, y)
      - triangle_size
      - triangle_rotation
    """
    md = metadata or {}
    size = float(md.get("triangle_size", size_mm))
    rot = float(md.get("triangle_rotation", rotation_deg))

    default_filled = (float(paper_width_mm) - float(margin_mm) - 18.0, float(base_y_mm))
    default_empty = (float(paper_width_mm) - float(margin_mm) - 34.0, float(base_y_mm))

    filled_center = md.get("triangle_filled_center", default_filled)
    empty_center = md.get("triangle_empty_center", default_empty)

    add_filled_triangle(layout, center=filled_center, size=size, rotation=rot, layer="SYMBOLS")
    add_empty_triangle(layout, center=empty_center, size=size, rotation=rot, layer="SYMBOLS")
