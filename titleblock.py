"""Title block unique bandeau bas + logo PNG compatible AutoCAD."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

from .sanitize import sanitize_layer_name, sanitize_text


def _rect(layout, x0, y0, x1, y1, layer):
    layout.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], dxfattribs={"layer": layer})


def _is_black_layer(layout: object, layer_name: str) -> bool:
    try:
        layer = layout.doc.layers.get(layer_name)
        return abs(int(layer.dxf.color)) == 7
    except Exception:
        return False


def _titleblock_text_color(layout: object, layer_name: str) -> int:
    return 256 if _is_black_layer(layout, layer_name) else 7


def _extract_qty_and_clean_designation(designation: object) -> Tuple[str, Optional[int]]:
    value = str(designation or "").strip()
    match = re.search(r"\(\s*x\s*(\d+)\s*\)", value, flags=re.IGNORECASE)
    if not match:
        return value, None
    qty = None
    try:
        qty = int(match.group(1))
    except Exception:
        qty = None
    cleaned = re.sub(r"\(\s*x\s*\d+\s*\)", "", value, flags=re.IGNORECASE).strip()
    return cleaned, qty


def add_logo(layout: object, logo_path: Optional[str], target_rect: Tuple[float, float, float, float]) -> bool:
    """Ajoute le vrai logo PNG via IMAGE/IMAGEDEF."""
    x0, y0, x1, y1 = target_rect
    w = max(1.0, float(x1) - float(x0))
    h = max(1.0, float(y1) - float(y0))

    layer_tb = sanitize_layer_name("TITLEBLOCK", fallback="TITLEBLOCK")

    candidate_paths = []
    if logo_path:
        candidate_paths.append(logo_path)
        candidate_paths.append(os.path.join(os.getcwd(), logo_path))
        candidate_paths.append(os.path.join(os.path.dirname(__file__), "..", logo_path))

    resolved_logo = None
    for path in candidate_paths:
        if path and os.path.isfile(path):
            resolved_logo = path
            break

    if resolved_logo and os.path.isfile(resolved_logo):
        try:
            px_size = (1000, 400)
            try:
                pil_mod = __import__("PIL.Image", fromlist=["Image"])
                with pil_mod.open(resolved_logo) as img:
                    px_size = tuple(img.size)
            except Exception:
                pass

            rel_path = os.path.relpath(resolved_logo, os.getcwd())
            image_def = layout.doc.add_image_def(filename=rel_path, size_in_pixel=px_size)
            layout.add_image(
                image_def,
                insert=(x0, y0),
                size_in_units=(w, h),
                dxfattribs={"layer": layer_tb},
            )
            return True
        except Exception:
            pass
    return False


def add_title_block(
    layout: object,
    paper_w: float = 420.0,
    paper_h: float = 297.0,
    margin: float = 10.0,
    metadata: Optional[Dict[str, Any]] = None,
    logo_path: Optional[str] = None,
    text_height: float = 3.0,
    titleblock_height: float = 32.0,
) -> bool:
    """Ajoute le cartouche unique (pas de légende séparée)."""
    metadata = metadata or {}

    layer_tb = sanitize_layer_name("TITLEBLOCK", fallback="TITLEBLOCK")
    layer_txt = sanitize_layer_name("TEXT", fallback="TEXT")
    layer_sym = sanitize_layer_name("SYMBOLS", fallback="SYMBOLS")

    for layer_name, color in ((layer_tb, 7), (layer_txt, 7), (layer_sym, 2)):
        if layer_name not in layout.doc.layers:
            layout.doc.layers.new(layer_name, dxfattribs={"color": color})

    try:
        from ezdxf.enums import TextEntityAlignment
    except Exception:
        TextEntityAlignment = None

    x_left = float(margin)
    x_right = float(paper_w) - float(margin)
    y_bottom = float(margin)
    y_top = float(margin) + float(titleblock_height)

    try:
        _rect(layout, x_left, y_bottom, x_right, y_top, layer_tb)
    except Exception:
        return False

    logo_width = 44.0
    col_y_split = y_bottom + max(10.0, float(titleblock_height) * 0.46)

    try:
        layout.add_line((x_left + logo_width, y_bottom), (x_left + logo_width, y_top), dxfattribs={"layer": layer_tb})
        layout.add_line((x_left + logo_width, col_y_split), (x_right, col_y_split), dxfattribs={"layer": layer_tb})
    except Exception:
        pass

    add_logo(layout, logo_path=logo_path, target_rect=(x_left + 2.0, y_bottom + 2.0, x_left + logo_width - 2.0, y_top - 2.0))

    content_x = x_left + logo_width + 2.0
    content_width = x_right - content_x - 2.0
    top_cols = 5
    col_width = content_width / float(top_cols)

    def _txt(value, x, y, h=text_height, align=None):
        text_color = _titleblock_text_color(layout, layer_txt)
        t = layout.add_text(
            sanitize_text(str(value), fallback="-"),
            dxfattribs={"layer": layer_txt, "height": float(h), "style": "Standard", "color": text_color},
        )
        if TextEntityAlignment and align is not None:
            t.set_placement((x, y), align=align)
        else:
            t.set_placement((x, y))

    designation_raw = metadata.get("part_name", metadata.get("designation", metadata.get("reference", "")))
    designation, qty_from_designation = _extract_qty_and_clean_designation(designation_raw)
    qty_value = metadata.get("quantity", metadata.get("qty", 1))
    if qty_from_designation is not None:
        qty_value = qty_from_designation

    top_fields = [
        ("DATE", metadata.get("date", "")),
        ("PROJECT", metadata.get("project_name", "")),
        ("BODY", metadata.get("corps_meuble", metadata.get("body", "caisson"))),
        ("PART", designation),
        ("QTY", qty_value),
    ]

    for idx, (label, value) in enumerate(top_fields):
        cx = content_x + col_width * idx + col_width * 0.5
        _txt(label, cx, y_top - 4.0, h=max(1.8, text_height * 0.60), align=TextEntityAlignment.MIDDLE_CENTER if TextEntityAlignment else None)
        _txt(value, cx, y_top - 10.0, h=max(2.2, text_height), align=TextEntityAlignment.MIDDLE_CENTER if TextEntityAlignment else None)

    # Traits verticaux entre chaque caisson (colonnes)
    try:
        for idx in range(1, top_cols):
            x_sep = content_x + col_width * idx
            layout.add_line((x_sep, y_bottom), (x_sep, y_top), dxfattribs={"layer": layer_tb})
    except Exception:
        pass

    bottom_text = f"CLIENT: {metadata.get('client', '')}   VERSION: {metadata.get('version', '')}   COMMENT: {metadata.get('comments', '')}"
    _txt(bottom_text, content_x + 1.0, y_bottom + 3.0, h=max(1.8, text_height * 0.72), align=TextEntityAlignment.LEFT if TextEntityAlignment else None)

    tri_cx = x_right - 20.0
    tri_cy = y_bottom + 6.0
    tri_s = 3.5
    layout.add_solid([(tri_cx, tri_cy + tri_s), (tri_cx - tri_s, tri_cy - tri_s), (tri_cx + tri_s, tri_cy - tri_s)], dxfattribs={"layer": layer_sym})
    layout.add_lwpolyline(
        [(tri_cx - 10.0, tri_cy + tri_s), (tri_cx - 13.5, tri_cy - tri_s), (tri_cx - 6.5, tri_cy - tri_s), (tri_cx - 10.0, tri_cy + tri_s)],
        dxfattribs={"layer": layer_sym},
    )
    _txt("TRI: FULL/EMPTY", tri_cx - 46.0, tri_cy - 1.0, h=max(1.8, text_height * 0.66), align=TextEntityAlignment.LEFT if TextEntityAlignment else None)

    return True


# Backward compatibility alias
def add_cartouche(*args, **kwargs):
    return add_title_block(*args, **kwargs)
