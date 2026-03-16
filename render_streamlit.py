"""Conversion Scene <-> Plotly pour garantir une source de vérité unique."""

from __future__ import annotations

import re
from typing import List, Tuple

from .scene import Arc, Circle, Dimension, HatchSimple, Line, Leader, Polyline, Scene, Text


def _equilateral_triangle_from_apex(apex, side, orientation):
    x, y = float(apex[0]), float(apex[1])
    s = float(side)
    h = s * (3.0 ** 0.5) / 2.0

    if orientation == "down":
        # Sommet au bord inférieur, triangle vers le haut (intérieur)
        return [
            (x, y),
            (x - s / 2.0, y + h),
            (x + s / 2.0, y + h),
        ]
    if orientation == "up":
        # Sommet au bord supérieur, triangle vers le bas (intérieur)
        return [
            (x, y),
            (x - s / 2.0, y - h),
            (x + s / 2.0, y - h),
        ]
    if orientation == "left":
        # Sommet au bord gauche, triangle vers la droite (intérieur)
        return [
            (x, y),
            (x + h, y - s / 2.0),
            (x + h, y + s / 2.0),
        ]
    if orientation == "right":
        # Sommet au bord droit, triangle vers la gauche (intérieur)
        return [
            (x, y),
            (x - h, y - s / 2.0),
            (x - h, y + s / 2.0),
        ]

    return [
        (x, y),
        (x - s / 2.0, y + h),
        (x + s / 2.0, y + h),
    ]


def _split_polyline_by_none(xs, ys):
    segments = []
    current = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            if len(current) >= 2:
                segments.append(current)
            current = []
            continue
        current.append((float(x), float(y)))
    if len(current) >= 2:
        segments.append(current)
    return segments


def _parse_plotly_path(path: str) -> List[Tuple[float, float]]:
    tokens = re.findall(r"[MLZmlz]|-?\d+(?:\.\d+)?", path or "")
    points = []
    idx = 0
    current_cmd = None
    while idx < len(tokens):
        tok = tokens[idx]
        if tok.upper() in ("M", "L", "Z"):
            current_cmd = tok.upper()
            idx += 1
            if current_cmd == "Z":
                break
            continue
        if current_cmd in ("M", "L") and idx + 1 < len(tokens):
            x = float(tokens[idx])
            y = float(tokens[idx + 1])
            points.append((x, y))
            idx += 2
            continue
        idx += 1
    return points


def _is_dimension_shape_line(shp, dims, tol=0.5, tick_len=6.0):
    if not dims:
        return False
    shape_type = (getattr(shp, "type", "") or "").lower()
    if shape_type != "line":
        return False

    try:
        x0, y0 = float(shp.x0), float(shp.y0)
        x1, y1 = float(shp.x1), float(shp.y1)
    except Exception:
        return False

    for dim in dims:
        axis = dim.get("axis")
        p1 = dim.get("p1") or (0.0, 0.0)
        p2 = dim.get("p2") or (0.0, 0.0)
        dim_line = dim.get("dim_line")

        try:
            p1x, p1y = float(p1[0]), float(p1[1])
            p2x, p2y = float(p2[0]), float(p2[1])
            dim_line = float(dim_line)
        except Exception:
            continue

        # Dimension line
        if axis == "x":
            if abs(y0 - dim_line) <= tol and abs(y1 - dim_line) <= tol:
                if min(p1x, p2x) - tol <= min(x0, x1) <= max(p1x, p2x) + tol:
                    return True
            # Extension lines
            if abs(x0 - x1) <= tol:
                if abs(x0 - p1x) <= tol or abs(x0 - p2x) <= tol:
                    if abs(y0 - dim_line) <= tol or abs(y1 - dim_line) <= tol:
                        return True
            # Tick marks
            if abs(x0 - x1) <= tol:
                if min(abs(x0 - p1x), abs(x0 - p2x)) <= tol:
                    if abs((y0 + y1) / 2.0 - dim_line) <= tol:
                        if abs(y0 - y1) <= tick_len * 2:
                            return True
        elif axis == "y":
            if abs(x0 - dim_line) <= tol and abs(x1 - dim_line) <= tol:
                if min(p1y, p2y) - tol <= min(y0, y1) <= max(p1y, p2y) + tol:
                    return True
            if abs(y0 - y1) <= tol:
                if abs(y0 - p1y) <= tol or abs(y0 - p2y) <= tol:
                    if abs(x0 - dim_line) <= tol or abs(x1 - dim_line) <= tol:
                        return True
            if abs(y0 - y1) <= tol:
                if min(abs(y0 - p1y), abs(y0 - p2y)) <= tol:
                    if abs((x0 + x1) / 2.0 - dim_line) <= tol:
                        if abs(x0 - x1) <= tick_len * 2:
                            return True
    return False


def convert_plotly_figure_to_scene(fig, name="SHEET") -> Scene:
    scene = Scene(name=name)

    meta = getattr(fig.layout, "meta", None) or {}
    dxf_dims = list(meta.get("dxf_dimensions", []))
    dim_labels = []
    for dim in dxf_dims:
        label = dim.get("label")
        text = dim.get("text")
        if label and text is not None:
            dim_labels.append((float(label[0]), float(label[1]), str(text)))

    for dim in dxf_dims:
        p1 = dim.get("p1")
        p2 = dim.get("p2")
        if not p1 or not p2:
            continue
        scene.entities.append(
            Dimension(
                layer="DIM",
                category="dimension",
                p1=(float(p1[0]), float(p1[1])),
                p2=(float(p2[0]), float(p2[1])),
                offset=float(dim.get("offset", 10.0)),
                text=str(dim.get("text")) if dim.get("text") is not None else None,
                axis=dim.get("axis", "auto"),
                side=dim.get("side"),
                dimstyle="POTECH_DIM",
                text_height=10.0,
            )
        )

    # Traiter les triangles depuis les métadonnées
    dxf_triangles = list(meta.get("dxf_triangles", []))
    for triangle in dxf_triangles:
        filled = triangle.get("filled", False)
        layer = triangle.get("layer", "GEOM")
        orientation = triangle.get("orientation", "down")
        center = triangle.get("center")
        size = triangle.get("size", 20.0)

        if center:
            pts = _equilateral_triangle_from_apex(center, float(size), orientation)
            scene.entities.append(Polyline(layer=layer, points=pts, closed=True))
            # Sécurisation DXF: ajouter explicitement le 3e côté en blanc
            # (relie les deux extrémités des 2 traits obliques)
            scene.entities.append(Line(layer=layer, color=7, start=pts[1], end=pts[2]))
            if filled:
                scene.entities.append(HatchSimple(layer=layer, boundary=pts, pattern="SOLID", scale=1.0))

    if fig.layout and fig.layout.shapes:
        for shp in fig.layout.shapes:
            layer = getattr(shp, "name", None) or "GEOM"
            shape_type = (getattr(shp, "type", "") or "").lower()

            if shape_type == "line":
                if _is_dimension_shape_line(shp, dxf_dims):
                    continue
                scene.entities.append(Line(layer=layer, start=(float(shp.x0), float(shp.y0)), end=(float(shp.x1), float(shp.y1))))
            elif shape_type == "rect":
                pts = [
                    (float(shp.x0), float(shp.y0)),
                    (float(shp.x1), float(shp.y0)),
                    (float(shp.x1), float(shp.y1)),
                    (float(shp.x0), float(shp.y1)),
                ]
                scene.entities.append(Polyline(layer=layer, points=pts, closed=True))
            elif shape_type == "circle":
                cx = (float(shp.x0) + float(shp.x1)) / 2.0
                cy = (float(shp.y0) + float(shp.y1)) / 2.0
                r = abs(float(shp.x1) - float(shp.x0)) / 2.0
                scene.entities.append(Circle(layer=layer, center=(cx, cy), radius=r))
            elif shape_type == "path":
                pts = _parse_plotly_path(getattr(shp, "path", ""))
                if len(pts) >= 2:
                    # Les paths sont maintenant gérés par les métadonnées pour les triangles
                    # On ne traite ici que les autres paths éventuels
                    pass

    for trace in fig.data or []:
        mode = (getattr(trace, "mode", "") or "").lower()
        layer = getattr(trace, "name", None) or "GEOM"

        xs = list(getattr(trace, "x", []) or [])
        ys = list(getattr(trace, "y", []) or [])
        texts = list(getattr(trace, "text", []) or [])

        if "lines" in mode and xs and ys:
            for seg in _split_polyline_by_none(xs, ys):
                scene.entities.append(Polyline(layer=layer, points=seg, closed=False))

        if "markers" in mode and xs and ys:
            marker_size = float(getattr(getattr(trace, "marker", None), "size", 6) or 6)
            radius = max(0.5, marker_size * 0.15)
            for x, y in zip(xs, ys):
                if x is None or y is None:
                    continue
                scene.entities.append(Circle(layer=layer, center=(float(x), float(y)), radius=radius))

        if "text" in mode and xs and ys and texts:
            for x, y, t in zip(xs, ys, texts):
                if x is None or y is None:
                    continue
                scene.entities.append(Text(layer="TEXT", category="text", text=str(t), insert=(float(x), float(y)), height=2.5, align="CENTER"))

    for ann in fig.layout.annotations or []:
        ann_text = str(getattr(ann, "text", ""))
        ann_x = float(getattr(ann, "x", 0.0))
        ann_y = float(getattr(ann, "y", 0.0))
        if dim_labels:
            for lx, ly, lt in dim_labels:
                if ann_text == lt and abs(ann_x - lx) <= 0.5 and abs(ann_y - ly) <= 0.5:
                    break
            else:
                scene.entities.append(Text(layer="TEXT", category="text", text=ann_text, insert=(ann_x, ann_y), height=2.5, align="CENTER"))
            continue
        scene.entities.append(Text(layer="TEXT", category="text", text=ann_text, insert=(ann_x, ann_y), height=2.5, align="CENTER"))

    if fig.layout and fig.layout.xaxis and fig.layout.yaxis:
        xr = getattr(fig.layout.xaxis, "range", None)
        yr = getattr(fig.layout.yaxis, "range", None)
        if xr and yr and len(xr) == 2 and len(yr) == 2:
            scene.width = abs(float(xr[1]) - float(xr[0]))
            scene.height = abs(float(yr[1]) - float(yr[0]))

    return scene


def render_scene_to_streamlit(scene: Scene):
    import plotly.graph_objects as go

    fig = go.Figure()

    for ent in scene.entities:
        if isinstance(ent, Line):
            fig.add_trace(go.Scatter(x=[ent.start[0], ent.end[0]], y=[ent.start[1], ent.end[1]], mode="lines", name=ent.layer, showlegend=False))
        elif isinstance(ent, Polyline):
            xs = [p[0] for p in ent.points]
            ys = [p[1] for p in ent.points]
            if ent.closed and ent.points:
                xs += [ent.points[0][0]]
                ys += [ent.points[0][1]]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=ent.layer, showlegend=False))
        elif isinstance(ent, Circle):
            x0, y0 = ent.center[0] - ent.radius, ent.center[1] - ent.radius
            x1, y1 = ent.center[0] + ent.radius, ent.center[1] + ent.radius
            fig.add_shape(type="circle", x0=x0, y0=y0, x1=x1, y1=y1)
        elif isinstance(ent, Arc):
            pass
        elif isinstance(ent, Text):
            fig.add_trace(go.Scatter(x=[ent.insert[0]], y=[ent.insert[1]], mode="text", text=[ent.text], showlegend=False))
        elif isinstance(ent, Leader):
            if len(ent.points) >= 2:
                fig.add_trace(go.Scatter(x=[p[0] for p in ent.points], y=[p[1] for p in ent.points], mode="lines", showlegend=False))
                if ent.text:
                    p = ent.points[-1]
                    fig.add_trace(go.Scatter(x=[p[0]], y=[p[1]], mode="text", text=[ent.text], showlegend=False))
        elif isinstance(ent, Dimension):
            fig.add_trace(go.Scatter(x=[ent.p1[0], ent.p2[0]], y=[ent.p1[1], ent.p2[1]], mode="lines", showlegend=False))
            label = ent.text or "DIM"
            fig.add_trace(go.Scatter(x=[(ent.p1[0]+ent.p2[0])/2], y=[(ent.p1[1]+ent.p2[1])/2], mode="text", text=[label], showlegend=False))
        elif isinstance(ent, HatchSimple):
            if len(ent.boundary) >= 3:
                pts = ent.boundary + [ent.boundary[0]]
                fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines", showlegend=False))

    fig.update_layout(title=scene.name, xaxis=dict(scaleanchor="y", scaleratio=1), yaxis=dict(), showlegend=False)
    return fig
