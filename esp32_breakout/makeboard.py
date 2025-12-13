# KiCad pcbnew Python script (KiCad 7/8)
# Export laser-ready SVG of a copper layer as FILLED geometry (no stroke widths).
# Includes: pads + tracks + vias + copper shapes on that layer.
# Default: EXCLUDES zones (to avoid the "stencil sheet" look).
#
# Run inside PCB Editor: Tools -> Scripting Console
#   exec(open(r"C:\path\to\export_laser_svg.py", "r", encoding="utf-8").read())

import os
import pcbnew

# ---------------- USER SETTINGS ----------------
LAYER_NAME = "F.Cu"          # "F.Cu" or "B.Cu"
INCLUDE_ZONES = False        # True if you really want copper pours/zones included
MAX_ERROR_MM = 0.02          # polygon approximation error (mm). Smaller => more points
MARGIN_MM = 1.0              # margin around extents (mm)
FILL_COLOR = "#000000"       # black fill
OUT_SUFFIX = "_laser.svg"    # output filename suffix
# ----------------------------------------------


def iu_from_mm(mm: float) -> int:
    return pcbnew.FromMM(mm)

def mm_from_iu(iu: int) -> float:
    return pcbnew.ToMM(iu)

def get_layer_id(board, name: str) -> int:
    # Works in KiCad 7/8
    try:
        return board.GetLayerID(name)
    except Exception:
        # fallback search
        for lid in range(pcbnew.PCB_LAYER_ID_COUNT):
            if board.GetLayerName(lid) == name:
                return lid
    raise RuntimeError(f"Could not find layer '{name}'")

def poly_boolean_add(dst, src):
    # KiCad naming differs a bit across builds; try common methods.
    for fn in ("BooleanAdd", "BooleanAddTo", "Add", "Append"):
        if hasattr(dst, fn):
            getattr(dst, fn)(src)
            return
    raise RuntimeError("Could not boolean-add polygon sets (KiCad API mismatch).")

def item_on_layer(item, lid: int) -> bool:
    # Robust layer test across item types
    try:
        if hasattr(item, "IsOnLayer"):
            return bool(item.IsOnLayer(lid))
    except Exception:
        pass

    try:
        if hasattr(item, "GetLayer"):
            return int(item.GetLayer()) == int(lid)
    except Exception:
        pass

    # Vias / some special items: accept and let TransformShapeToPolygon decide
    # (but only if they plausibly touch copper; we can't always know here)
    try:
        cls = item.GetClass()
        if "VIA" in cls.upper():
            return True
    except Exception:
        pass

    return False

def transform_to_polyset(item, max_error_iu: int):
    # Convert the TRUE shape (with width) into polygon(s)
    ps = pcbnew.SHAPE_POLY_SET()

    # Common KiCad signature: TransformShapeToPolygon(polyset, clearance, maxError, ...)
    for args in (
        (ps, 0, max_error_iu),
        (ps, 0, max_error_iu, True),
        (ps, 0, max_error_iu, False),
    ):
        try:
            item.TransformShapeToPolygon(*args)
            return ps
        except Exception:
            pass

    return None

def zone_to_polyset(zone, max_error_iu: int):
    ps = pcbnew.SHAPE_POLY_SET()

    # Prefer solid filled areas if available
    for fn in ("TransformSolidAreasToPolygon", "TransformSolidAreasShapesToPolygon"):
        if hasattr(zone, fn):
            try:
                getattr(zone, fn)(ps, 0, max_error_iu)
                return ps
            except Exception:
                pass

    # Fallback: treat like a generic item
    zps = transform_to_polyset(zone, max_error_iu)
    return zps

def iter_polyset_loops(polyset):
    """
    Yield loops (list of points) for SVG.
    Best case: iterate polygons + holes.
    Fallback: iterate outlines.
    Points are pcbnew.VECTOR2I.
    """
    # KiCad 7/8 typically has PolygonCount / Outline / HoleCount / Hole
    if hasattr(polyset, "PolygonCount") and hasattr(polyset, "Outline"):
        try:
            pc = polyset.PolygonCount()
            for p in range(pc):
                # outer outline
                outer = polyset.Outline(p)
                yield outer

                # holes
                if hasattr(polyset, "HoleCount") and hasattr(polyset, "Hole"):
                    hc = polyset.HoleCount(p)
                    for h in range(hc):
                        hole = polyset.Hole(p, h)
                        yield hole
            return
        except Exception:
            pass

    # Fallback: iterate outlines only
    if hasattr(polyset, "OutlineCount") and hasattr(polyset, "Outline"):
        oc = polyset.OutlineCount()
        for i in range(oc):
            yield polyset.Outline(i)
        return

    raise RuntimeError("Could not iterate polygon loops (KiCad API mismatch).")

def chain_to_points_mm(chain, dx_mm: float, dy_mm: float):
    pts = []

    if hasattr(chain, "PointCount") and hasattr(chain, "CPoint"):
        n = chain.PointCount()
        for i in range(n):
            p = chain.CPoint(i)
            pts.append((mm_from_iu(p.x) + dx_mm, mm_from_iu(p.y) + dy_mm))
        return pts

    # fallback iterator
    try:
        for p in chain:
            pts.append((mm_from_iu(p.x) + dx_mm, mm_from_iu(p.y) + dy_mm))
        return pts
    except Exception:
        pass

    return pts

def polyset_bounds_mm(polyset):
    minx = 1e18
    miny = 1e18
    maxx = -1e18
    maxy = -1e18

    for chain in iter_polyset_loops(polyset):
        pts = chain_to_points_mm(chain, 0.0, 0.0)
        for x, y in pts:
            if x < minx: minx = x
            if y < miny: miny = y
            if x > maxx: maxx = x
            if y > maxy: maxy = y

    if minx > 1e17:
        raise RuntimeError("Bounds failed: polyset appears empty.")
    return minx, miny, maxx, maxy

def polyset_to_svg_paths(polyset, dx_mm: float, dy_mm: float):
    paths = []
    for chain in iter_polyset_loops(polyset):
        pts = chain_to_points_mm(chain, dx_mm, dy_mm)
        if len(pts) < 3:
            continue
        d = [f"M {pts[0][0]:.4f},{pts[0][1]:.4f}"]
        for x, y in pts[1:]:
            d.append(f"L {x:.4f},{y:.4f}")
        d.append("Z")
        paths.append(" ".join(d))
    return paths

def main():
    board = pcbnew.GetBoard()
    if not board:
        raise RuntimeError("No board loaded. Open a .kicad_pcb in PCB Editor first.")

    lid = get_layer_id(board, LAYER_NAME)
    max_error_iu = iu_from_mm(MAX_ERROR_MM)

    combined = pcbnew.SHAPE_POLY_SET()
    added = 0

    # ---- 1) Tracks + vias (board.GetTracks) ----
    try:
        for t in list(board.GetTracks()):
            # Vias can be on multiple layers; allow them through item_on_layer=True
            if not item_on_layer(t, lid):
                continue
            ps = transform_to_polyset(t, max_error_iu)
            if ps is not None:
                poly_boolean_add(combined, ps)
                added += 1
    except Exception:
        pass

    # ---- 2) Copper "drawings"/shapes on that layer (arcs, segments, etc.) ----
    # This is the part your last script missed, which is why you got "pads only".
    try:
        for d in list(board.GetDrawings()):
            if not item_on_layer(d, lid):
                continue
            ps = transform_to_polyset(d, max_error_iu)
            if ps is not None:
                poly_boolean_add(combined, ps)
                added += 1
    except Exception:
        pass

    # ---- 3) Pads ----
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            on_layer = False
            try:
                on_layer = pad.IsOnLayer(lid)
            except Exception:
                try:
                    on_layer = pad.GetLayerSet().Contains(lid)
                except Exception:
                    on_layer = False

            if not on_layer:
                continue

            ps = transform_to_polyset(pad, max_error_iu)
            if ps is not None:
                poly_boolean_add(combined, ps)
                added += 1

    # ---- 4) Zones (optional) ----
    if INCLUDE_ZONES:
        try:
            for z in board.Zones():
                try:
                    if z.GetLayer() != lid:
                        continue
                except Exception:
                    continue
                zps = zone_to_polyset(z, max_error_iu)
                if zps is not None:
                    poly_boolean_add(combined, zps)
                    added += 1
        except Exception:
            pass

    if added == 0:
        raise RuntimeError(
            f"Nothing exported on {LAYER_NAME}. "
            f"Double-check LAYER_NAME and that copper exists on that layer."
        )

    # Bounds + margin + shift to positive coords
    minx, miny, maxx, maxy = polyset_bounds_mm(combined)
    minx -= MARGIN_MM
    miny -= MARGIN_MM
    maxx += MARGIN_MM
    maxy += MARGIN_MM

    width = maxx - minx
    height = maxy - miny
    dx = -minx
    dy = -miny

    paths = polyset_to_svg_paths(combined, dx, dy)

    # SVG: use evenodd to properly handle holes if they come through
    svg = []
    svg.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.4f}mm" height="{height:.4f}mm" '
        f'viewBox="0 0 {width:.4f} {height:.4f}">'
    )
    svg.append(f'<g fill="{FILL_COLOR}" stroke="none" fill-rule="evenodd">')
    for d in paths:
        svg.append(f'  <path d="{d}"/>')
    svg.append('</g></svg>')

    pcb_path = board.GetFileName()
    if not pcb_path:
        raise RuntimeError("Board has no filename. Save the PCB first.")

    out_path = os.path.splitext(pcb_path)[0] + f"_{LAYER_NAME.replace('.','_')}" + OUT_SUFFIX
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))

    print(f"[OK] Wrote: {out_path}")
    print(f"Layer: {LAYER_NAME} | Zones included: {INCLUDE_ZONES}")
    print("Import into LightBurn: geometry should be FILLED shapes (not hairlines).")

main()
