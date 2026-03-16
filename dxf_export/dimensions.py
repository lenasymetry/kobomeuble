"""Rendu des cotations: DIMENSION AutoCAD prioritaire + fallback primitives."""

from __future__ import annotations

import math

from .sanitize import sanitize_layer_name, sanitize_table_name, sanitize_text


def ensure_potech_dimstyle(doc, dimstyle_name="POTECH_DIM", text_height=12.0, arrow_size=3.0, dimgap=1.2):
    """Crée un DIMSTYLE minimal robuste R2010."""
    safe_name = sanitize_table_name(dimstyle_name, fallback="POTECH_DIM")
    if safe_name in doc.dimstyles:
        return safe_name

    if "Standard" not in doc.styles:
        doc.styles.new("Standard", dxfattribs={"font": "txt"})

    doc.dimstyles.new(
        safe_name,
        dxfattribs={
            "dimtxsty": "Standard",
            "dimtxt": float(text_height),
            "dimgap": float(dimgap),
            "dimasz": float(arrow_size),
            "dimclrd": 0,
            "dimclre": 0,
            "dimclrt": 0,
            "dimdec": 1,
            "dimtix": 0,
            "dimexo": 1.0,
        },
    )
    return safe_name


def _resolve_dimension_axis(dim):
    x1, y1 = float(dim.p1[0]), float(dim.p1[1])
    x2, y2 = float(dim.p2[0]), float(dim.p2[1])
    if dim.axis == "x":
        return "x"
    if dim.axis == "y":
        return "y"
    return "x" if abs(y2 - y1) <= abs(x2 - x1) else "y"


def add_dimension_autocad(layout, dim_data, dimstyle="POTECH_DIM", text_height=12.0, arrow_size=3.0, dimgap=1.2):
    """Ajoute une vraie DIMENSION AutoCAD (associative au sens AutoCAD, non simulée)."""
    layer_name = sanitize_layer_name(getattr(dim_data, "layer", None) or "DIM", fallback="DIM")
    if layer_name not in layout.doc.layers:
        layout.doc.layers.new(layer_name, dxfattribs={"color": 1})

    dimstyle_name = ensure_potech_dimstyle(layout.doc, dimstyle_name=dimstyle, text_height=text_height, arrow_size=arrow_size, dimgap=dimgap)

    x1, y1 = float(dim_data.p1[0]), float(dim_data.p1[1])
    x2, y2 = float(dim_data.p2[0]), float(dim_data.p2[1])
    offset = float(getattr(dim_data, "dim_line_offset", getattr(dim_data, "offset", 10.0)))
    side = (getattr(dim_data, "side", None) or "").lower()
    axis = _resolve_dimension_axis(dim_data)

    if axis == "x":
        if side == "bottom":
            y_dim = min(y1, y2) - offset
        else:
            y_dim = max(y1, y2) + offset
        base = (min(x1, x2), y_dim)
        override = layout.add_linear_dim(
            base=base,
            p1=(x1, y1),
            p2=(x2, y2),
            angle=0,
            dimstyle=dimstyle_name,
            dxfattribs={"layer": layer_name},
        )
    else:
        if side == "left":
            x_dim = min(x1, x2) - offset
        else:
            x_dim = max(x1, x2) + offset
        base = (x_dim, min(y1, y2))
        override = layout.add_linear_dim(
            base=base,
            p1=(x1, y1),
            p2=(x2, y2),
            angle=90,
            dimstyle=dimstyle_name,
            dxfattribs={"layer": layer_name},
        )

    text_override = getattr(dim_data, "text_override", None) or getattr(dim_data, "text", None)
    if text_override:
        try:
            override.dimension.dxf.text = sanitize_text(str(text_override), fallback="<>")
        except Exception:
            pass

    override.render()
    return override


def _draw_arrow_triangle(layout, tip, direction, size, layer):
    ux, uy = direction
    norm = math.hypot(ux, uy)
    if norm == 0:
        return
    ux, uy = ux / norm, uy / norm
    nx, ny = -uy, ux
    bx = tip[0] - ux * size
    by = tip[1] - uy * size
    p1 = (bx + nx * size * 0.45, by + ny * size * 0.45)
    p2 = (bx - nx * size * 0.45, by - ny * size * 0.45)
    layout.add_lwpolyline([tip, p1, p2, tip], dxfattribs={"layer": layer})


def add_dimensions_as_primitives(layout, dim, text_height=10.0, arrow_size=3.0, text_style="Standard"):
    """Cotation ultra-compatible: LINE + flèches + TEXT.
    
    Args:
        layout: ezdxf layout (ModelSpace ou PaperSpace)
        dim: Dimension object avec (p1, p2, offset, axis, side, text_height)
        text_height: Hauteur texte en mm (défaut: 10.0 pour respect coords Streamlit)
        arrow_size: Taille flèches en mm
        text_style: Style texte DXF
    
    respect_dim_text_height = dim.text_height if dim.text_height is not None else text_height
    """
    p1 = dim.p1
    p2 = dim.p2
    offset = float(dim.offset)
    final_text_height = dim.text_height if dim.text_height is not None else text_height
    layer_name = sanitize_layer_name(dim.layer or "DIMS", fallback="DIMS")

    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])

    # Détermine axe: x/y ou auto (minimum de la variation)
    horizontal = (dim.axis == "x") or (dim.axis == "auto" and abs(y2 - y1) <= abs(x2 - x1))
    
    if horizontal:
        # Cotation horizontale: texte au dessus (ou selon 'side')
        if dim.side == "bottom":
            yy = min(y1, y2) - offset
        else:
            yy = max(y1, y2) + offset  # Défaut: top
        
        layout.add_line((x1, y1), (x1, yy), dxfattribs={"layer": layer_name})
        layout.add_line((x2, y2), (x2, yy), dxfattribs={"layer": layer_name})
        layout.add_line((x1, yy), (x2, yy), dxfattribs={"layer": layer_name})
        _draw_arrow_triangle(layout, (x1, yy), (1.0, 0.0), arrow_size, layer_name)
        _draw_arrow_triangle(layout, (x2, yy), (-1.0, 0.0), arrow_size, layer_name)

        label = sanitize_text(dim.text or f"{abs(x2 - x1):.1f}", fallback=f"{abs(x2 - x1):.1f}")
        ent = layout.add_text(
            label,
            dxfattribs={
                "layer": layer_name,
                "height": final_text_height,
                "style": sanitize_table_name(text_style, fallback="Standard"),
            },
        )
        mid_y = yy + (max(1.0, final_text_height * 0.6) if dim.side != "bottom" else -max(1.0, final_text_height * 0.6))
        ent.set_placement(((x1 + x2) / 2.0, mid_y), align="MIDDLE_CENTER")
        return
    
    # Cotation verticale: texte à droite (ou selon 'side')
    if dim.side == "left":
        xx = min(x1, x2) - offset
    else:
        xx = max(x1, x2) + offset  # Défaut: right
    
    layout.add_line((x1, y1), (xx, y1), dxfattribs={"layer": layer_name})
    layout.add_line((x2, y2), (xx, y2), dxfattribs={"layer": layer_name})
    layout.add_line((xx, y1), (xx, y2), dxfattribs={"layer": layer_name})
    _draw_arrow_triangle(layout, (xx, y1), (0.0, 1.0), arrow_size, layer_name)
    _draw_arrow_triangle(layout, (xx, y2), (0.0, -1.0), arrow_size, layer_name)

    label = sanitize_text(dim.text or f"{abs(y2 - y1):.1f}", fallback=f"{abs(y2 - y1):.1f}")
    ent = layout.add_text(
        label,
        dxfattribs={
            "layer": layer_name,
            "height": final_text_height,
            "style": sanitize_table_name(text_style, fallback="Standard"),
        },
    )
    mid_x = xx + (max(1.0, final_text_height * 0.6) if dim.side != "left" else -max(1.0, final_text_height * 0.6))
    ent.set_placement((mid_x, (y1 + y2) / 2.0), align="LEFT")


def add_dimensions_editable(layout, dim):
    """Compatibilité API existante: route vers add_dimension_autocad()."""
    return add_dimension_autocad(
        layout,
        dim_data=dim,
        dimstyle=getattr(dim, "dimstyle", "POTECH_DIM") or "POTECH_DIM",
        text_height=float(getattr(dim, "text_height", None) or 12.0),
    )
