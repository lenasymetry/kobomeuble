"""Gestion layouts PaperSpace + viewport auto-fit pour DXF multi-feuilles."""

from __future__ import annotations

from typing import Tuple

from .sanitize import sanitize_table_name


def setup_layout_with_viewport(
    doc,
    layout_name: str,
    paper_width_mm: float = 420.0,
    paper_height_mm: float = 297.0,
    margin_mm: float = 10.0,
):
    """Crée/initialise un layout A3 paysage avec un viewport flottant unique.

    Retourne: (layout, viewport)
    """
    safe_layout_name = sanitize_table_name(layout_name, fallback="SHEET_01", max_len=31)

    if safe_layout_name in doc.layouts:
        layout = doc.layouts.get(safe_layout_name)
    else:
        layout = doc.layouts.new(safe_layout_name)

    try:
        layout.page_setup(
            size=(float(paper_width_mm), float(paper_height_mm)),
            margins=(float(margin_mm), float(margin_mm), float(margin_mm), float(margin_mm)),
            units="mm",
            offset=(0.0, 0.0),
            rotation=0,
            scale=(1, 1),
            name="",
            device="DWG To PDF.pc3",
        )
    except Exception:
        # fallback si version ezdxf ne supporte pas tous les paramètres
        try:
            layout.page_setup(size=(float(paper_width_mm), float(paper_height_mm)), margins=(float(margin_mm),) * 4, units="mm")
        except Exception:
            pass

    # Nettoie les viewports flottants existants (status > 1)
    for vp in list(layout.query("VIEWPORT")):
        try:
            if int(getattr(vp.dxf, "status", 0) or 0) > 1:
                layout.delete_entity(vp)
        except Exception:
            continue

    viewport_center_ps = (float(paper_width_mm) / 2.0, float(paper_height_mm) / 2.0)
    viewport_size_ps = (
        max(1.0, float(paper_width_mm) - 2.0 * float(margin_mm)),
        max(1.0, float(paper_height_mm) - 2.0 * float(margin_mm)),
    )

    viewport = layout.add_viewport(
        center=viewport_center_ps,
        size=viewport_size_ps,
        view_center_point=(0.0, 0.0),
        view_height=100.0,
        status=2,
        dxfattribs={"layer": "VIEWPORTS"},
    )

    # verrouille le viewport (bit 0x4000)
    try:
        flags = int(getattr(viewport.dxf, "flags", 0) or 0)
        viewport.dxf.flags = flags | 0x4000
    except Exception:
        pass

    return layout, viewport


def setup_layout_with_viewport_excluding_titleblock(
    doc,
    layout_name: str,
    paper_width_mm: float = 420.0,
    paper_height_mm: float = 297.0,
    margin_mm: float = 10.0,
    titleblock_height_mm: float = 32.0,
):
    """Crée un layout avec 1 viewport limité à la zone au-dessus du cartouche."""
    safe_layout_name = sanitize_table_name(layout_name, fallback="SHEET_01", max_len=31)

    if safe_layout_name in doc.layouts:
        layout = doc.layouts.get(safe_layout_name)
    else:
        layout = doc.layouts.new(safe_layout_name)

    try:
        layout.page_setup(
            size=(float(paper_width_mm), float(paper_height_mm)),
            margins=(float(margin_mm), float(margin_mm), float(margin_mm), float(margin_mm)),
            units="mm",
            offset=(0.0, 0.0),
            rotation=0,
            scale=(1, 1),
            name="",
            device="DWG To PDF.pc3",
        )
    except Exception:
        try:
            layout.page_setup(size=(float(paper_width_mm), float(paper_height_mm)), margins=(float(margin_mm),) * 4, units="mm")
        except Exception:
            pass

    for vp in list(layout.query("VIEWPORT")):
        try:
            if int(getattr(vp.dxf, "status", 0) or 0) > 1:
                layout.delete_entity(vp)
        except Exception:
            continue

    draw_w = max(1.0, float(paper_width_mm) - 2.0 * float(margin_mm))
    draw_h = max(1.0, float(paper_height_mm) - 2.0 * float(margin_mm) - float(titleblock_height_mm))
    draw_bottom = float(margin_mm) + float(titleblock_height_mm)

    viewport_center_ps = (
        float(margin_mm) + draw_w / 2.0,
        draw_bottom + draw_h / 2.0,
    )

    viewport = layout.add_viewport(
        center=viewport_center_ps,
        size=(draw_w, draw_h),
        view_center_point=(0.0, 0.0),
        view_height=100.0,
        status=2,
        dxfattribs={"layer": "VIEWPORTS"},
    )

    try:
        flags = int(getattr(viewport.dxf, "flags", 0) or 0)
        viewport.dxf.flags = flags | 0x4000
    except Exception:
        pass

    return layout, viewport, {
        "draw_zone": {
            "left": float(margin_mm),
            "bottom": draw_bottom,
            "width": draw_w,
            "height": draw_h,
            "top": draw_bottom + draw_h,
        }
    }


def fit_viewport_to_bbox(
    viewport,
    bbox: Tuple[float, float, float, float],
    margin_factor: float = 1.05,
    min_view_height: float = 10.0,
):
    """Ajuste un viewport à la bbox géométrique, sans déformation.

    - centre vue = centre bbox
    - hauteur vue = max(hauteur_bbox, largeur_bbox/aspect_viewport) * marge
    """
    min_x, min_y, max_x, max_y = [float(v) for v in bbox]

    bbox_w = max(1e-6, max_x - min_x)
    bbox_h = max(1e-6, max_y - min_y)
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0

    vp_w = max(1e-6, float(getattr(viewport.dxf, "width", 1.0) or 1.0))
    vp_h = max(1e-6, float(getattr(viewport.dxf, "height", 1.0) or 1.0))
    vp_aspect = vp_w / vp_h

    target_h = max(bbox_h, bbox_w / vp_aspect)
    view_h = max(float(min_view_height), target_h * max(1.0, float(margin_factor)))

    viewport.dxf.view_center_point = (cx, cy)
    viewport.dxf.view_height = view_h

    # relock viewport
    try:
        flags = int(getattr(viewport.dxf, "flags", 0) or 0)
        viewport.dxf.flags = flags | 0x4000
    except Exception:
        pass

    return {
        "view_center": (cx, cy),
        "view_height": view_h,
        "bbox": (min_x, min_y, max_x, max_y),
        "bbox_size": (bbox_w, bbox_h),
    }
