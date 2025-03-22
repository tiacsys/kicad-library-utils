#!/usr/bin/env python3

import collections
import math
import sys
import warnings
from fnmatch import fnmatch
from pathlib import Path

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (
        common := Path(__file__).parent.parent.with_name("common").absolute()
    ) not in sys.path:
        sys.path.insert(0, str(common))

from svg_util import Tag, add_bboxes, bbox, define_arc, setup_svg

LAYERS = [
    "Names",
    "Hole_Plated",
    "Hole_Nonplated",
    "F_Adhes",
    "B_Adhes",
    "F_Paste",
    "B_Paste",
    "F_SilkS",
    "B_SilkS",
    "F_Mask",
    "B_Mask",
    "Dwgs_User",
    "Cmts_User",
    "Eco1_User",
    "Eco2_User",
    "Edge_Cuts",
    "Margin",
    "F_CrtYd",
    "B_CrtYd",
    "F_Fab",
    "B_Fab",
    "User_1",
    "User_2",
    "User_3",
    "User_4",
    "User_5",
    "User_6",
    "User_7",
    "User_8",
    "User_9",
    "F_Cu",
    "B_Cu",
]


def layerclass(layer, fill_or_stroke):
    assert fill_or_stroke in ("fill", "stroke")
    layer = layer.replace(".", "_")
    fill_or_stroke = fill_or_stroke[0]
    return f"l-{layer}-{fill_or_stroke}"


def elem_style(elem):
    if elem.get("width"):

        if elem.get("fill"):
            elem_cls = (
                layerclass(elem["layer"], "fill")
                + " "
                + layerclass(elem["layer"], "stroke")
            )
        else:
            elem_cls = layerclass(elem["layer"], "stroke")

        return {
            "class": elem_cls,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "stroke-width": elem["width"],
        }
    else:
        return {
            "class": layerclass(elem["layer"], "fill"),
        }


def render_line(line, **style):
    x1, y1 = line["start"]["x"], line["start"]["y"]
    x2, y2 = line["end"]["x"], line["end"]["y"]
    yield bbox((x1, y1), (x2, y2)), Tag(
        "path", **style, d=f"M {x1:.6f} {y1:.6f} L {x2:.6f} {y2:.6f}"
    )


def render_rect(rect, **style):
    x1, y1 = rect["start"]["x"], rect["start"]["y"]
    x2, y2 = rect["end"]["x"], rect["end"]["y"]
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    w, h = abs(x2 - x1), abs(y1 - y2)
    yield (x1, y1, x2, y2), Tag("rect", **style, x=x1, y=y1, width=w, height=h)


def render_circle(circle, **style):
    if "diameter" in circle:  # the sane variant
        r = circle["diameter"] / 2

    elif "end" in circle:  # the not sane variant
        r = math.hypot(
            circle["end"]["x"] - circle["center"]["x"],
            circle["end"]["y"] - circle["center"]["y"],
        )

    x, y = circle["center"]["x"], circle["center"]["y"]
    yield (x - r, y - r, x + r, y + r), Tag("circle", **style, cx=x, cy=y, r=r)


def render_text(text, **style):
    content = text.get(
        "reference", text.get("value", text.get("user"))
    )  # bad API design
    x, y = text["pos"]["x"], text["pos"]["y"]
    if (rot := text["pos"].get("orientation")) in (90, 270):
        xform = {"transform": f"rotate({-rot} {x} {y})"}
    else:
        xform = {}
    size = text["font"]["height"] / 2 or 0.5

    yield (x, y, x, y), Tag(
        "text",
        [content],
        font_family="monospace",
        font_size=f"{size:.3f}mm",
        x=x,
        y=y,
        dominant_baseline="middle",
        text_anchor="middle",
        **style,
        **xform,
    )


def render_drill(pad, **style):
    drill = pad.get("drill")
    if not drill:
        return

    px = pad["pos"]["x"]
    py = pad["pos"]["y"]

    x = px - drill["offset"].get("x", 0)
    y = py - drill["offset"].get("y", 0)
    w, h = drill["size"]["x"], drill["size"]["y"]

    # For now KiCad doesn't support drills with different orientations
    # to the pads, so we can just use the pad orientation.
    angle = pad["pos"]["orientation"]
    transform = f"rotate({-angle} {px} {py})"

    if drill["shape"] == "circular":
        assert w == h
        yield (x - w / 2, y - w / 2, x + w / 2, y + w / 2), Tag(
            "circle", **style, cx=x, cy=y, r=w / 2
        )
    else:
        assert drill["shape"] == "oval"

        elem_bbox = bbox((x - w / 2, y - h / 2), (x + w / 2, y + h / 2))

        yield elem_bbox, Tag(
            "rect",
            **style,
            x=x - w / 2,
            y=y - h / 2,
            transform=transform,
            width=w,
            height=h,
            rx=min(w, h) / 2,
        )


def _render_polygon_by_points(pts: list, **style):
    points = [(pt["x"], pt["y"]) for pt in pts]
    path_data = "M " + " L ".join(f"{x:.6f} {y:.6f}" for x, y in points)
    # Polygons are closed by definition
    path_data += " Z"
    return bbox(*points), Tag("path", **style, d=path_data)


def render_polygon(polygon, **style):
    points = polygon.get("points", polygon.get("pts"))  # bad API
    yield _render_polygon_by_points(points, **style)


def render_zone(zone, **style):
    points = zone.get("points")
    yield _render_polygon_by_points(points, **style)


def render_arc(arc, **style):
    # KiCad arcs are defined by three points: start, mid, end.
    x1, y1 = arc["start"]["x"], arc["start"]["y"]
    x2, y2 = arc["mid"]["x"], arc["mid"]["y"]
    x3, y3 = arc["end"]["x"], arc["end"]["y"]

    c, r, collinear, large_arc, is_circle = define_arc(
        (x1, y1), (x2, y2), (x3, y3), False
    )

    if is_circle:
        elem_bbox = bbox((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        yield elem_bbox, Tag("circle", **style, cx=c[0], cy=c[1], r=r)
        return
    if collinear:
        # The points are collinear, so we just draw a line
        elem_bbox = bbox((x1, y1), (x2, y2))
        yield elem_bbox, Tag(
            "path", **style, d=f"M {x1:.6f} {y1:.6f} L {x2:.6f} {y2:.6f}"
        )
        return

    large_arc = int(large_arc)
    sweep = 1

    d = f"M {x1:.6f} {y1:.6f} A {r:.6f} {r:.6f} 0 {large_arc} {sweep} {x3:.6f} {y3:.6f}"
    # We just approximate the bbox here with that of a circle. Calculating precise arc bboxes is
    # hairy, and unnecessary for our purposes.
    elem_bbox = bbox((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
    yield elem_bbox, Tag("path", **style, d=d)


def render_pad_circle(pad, layer, **style):
    x, y = pad["pos"]["x"], pad["pos"]["y"]
    r = pad["size"]["x"] / 2
    yield (x - r, y - r, x + r, y + r), Tag("circle", **style, cx=x, cy=y, r=r)


def render_pad_rect(pad, layer, **style):
    x, y = pad["pos"]["x"], pad["pos"]["y"]
    w, h = pad["size"]["x"], pad["size"]["y"]

    angle = pad["pos"]["orientation"]
    transform = f"rotate({-angle} {x} {y})"

    elem_bbox = bbox((x - w / 2, y - h / 2), (x + w / 2, y + h / 2))

    yield elem_bbox, Tag(
        "rect",
        **style,
        transform=transform,
        x=x - w / 2,
        y=y - h / 2,
        width=w,
        height=h,
    )


def render_pad_roundrect(pad, layer, **style):
    x, y = pad["pos"]["x"], pad["pos"]["y"]
    w, h = pad["size"]["x"], pad["size"]["y"]
    rx = min(w, h) * pad["roundrect_rratio"]

    angle = pad["pos"]["orientation"]
    transform = f"rotate({-angle} {x} {y})"

    elem_bbox = bbox((x - w / 2, y - h / 2), (x + w / 2, y + h / 2))

    yield elem_bbox, Tag(
        "rect",
        **style,
        transform=transform,
        x=x - w / 2,
        y=y - h / 2,
        width=w,
        height=h,
        rx=rx,
    )


def render_pad_oval(pad, layer, **style):
    x, y = pad["pos"]["x"], pad["pos"]["y"]
    w, h = pad["size"]["x"], pad["size"]["y"]

    angle = pad["pos"]["orientation"]
    transform = f"rotate({-angle} {x} {y})"
    elem_bbox = bbox((x - w / 2, y - h / 2), (x + w / 2, y + h / 2))

    yield elem_bbox, Tag(
        "rect",
        **style,
        transform=transform,
        x=x - w / 2,
        y=y - h / 2,
        width=w,
        height=h,
        rx=min(w, h) / 2,
    )


def render_pad_trapezoid(pad, layer, **style):
    # TODO, so far only used very rarely.
    warnings.warn("SVG export of trapezoid pads is not yet supported.")
    return ()


def render_pad_custom(pad, layer, **style):
    x, y = pad["pos"]["x"], pad["pos"]["y"]
    for prim in pad["primitives"]:
        prim_style = dict(style)
        prim["layer"] = layer
        if "width" in prim:
            prim_style.update(elem_style(prim))
            prim_style["class"] += " " + style["class"]

        angle = pad["pos"]["orientation"]
        transform = f"rotate({-angle} {x} {y}) translate({x} {y})"
        prim_style["transform"] = transform

        if prim["type"] == "gr_line":
            yield from render_line(prim, **prim_style)
        elif prim["type"] == "gr_poly":
            yield from render_polygon(prim, **prim_style)
        elif prim["type"] == "gr_arc":
            yield from render_arc(prim, **prim_style)
        elif prim["type"] == "gr_circle":
            yield from render_circle(prim, **prim_style)
        elif prim["type"] == "gr_rect":
            yield from render_rect(prim, **prim_style)

    anchor = pad["options"]["anchor"]

    # the anchor is always filled
    style["class"] += " " + layerclass(layer, "fill")

    if anchor == "rect":
        yield from render_pad_rect(pad, layer, **style)
    elif anchor == "circle":
        yield from render_pad_circle(pad, layer, **style)


def _render_mod_internal(mod):
    for fun, elems in [
        (render_line, mod.lines),
        (render_rect, mod.rects),
        (render_circle, mod.circles),
        (render_polygon, mod.polys),
        (render_arc, mod.arcs),
        (render_text, mod.userText),
        (render_text, [mod.reference, mod.value]),
    ]:
        # Single-layer elements
        for elem in elems:
            for bbox, tag in fun(elem, **elem_style(elem)):  # NOQA: F402
                yield elem["layer"], bbox, tag

    for pad in mod.pads:
        fun = globals()[f'render_pad_{pad["shape"]}']

        if "number" in pad:
            x, y = pad["pos"]["x"], pad["pos"]["y"]
            yield "Names", (x, y, x, y), Tag(
                "text",
                [pad["number"]],
                font_family="monospace",
                font_size="0.2px",
                x=x,
                y=y,
                dominant_baseline="middle",
                text_anchor="middle",
                **{"class": "l-Names-f"},
            )

        for layer in LAYERS:
            if any(
                fnmatch(layer, l.replace(".", "_")) for l in pad["layers"]  # NOQA: E741
            ):

                # Custom pads are rendered by their primitives, which can have fills or not
                if pad["shape"] == "custom":
                    style = {"class": ""}
                else:
                    # Normal pads are always filled
                    style = {"class": layerclass(layer, "fill")}

                for bbox, tag in fun(pad, layer, **style):
                    yield layer, bbox, tag

        if pad["drill"]:
            if pad["type"] == "thru_hole":
                layer = "Hole_Plated"
            elif pad["type"] == "np_thru_hole":
                layer = "Hole_Nonplated"
            else:
                # SMD pads don't have drills, but they *can* have an offset
                # which is in the drill structure.
                continue

            for bbox, tag in render_drill(pad, **{"class": f"l-{layer}-f"}):
                yield layer, bbox, tag

    for zone in mod.zones:

        for layer in zone["layers"]:
            style = {"class": layerclass(layer, "fill")}

            for bbox, tag in render_zone(zone, **style):
                yield layer, bbox, tag


def render_mod(mod: kicad_mod.KicadMod) -> str:
    tags = collections.defaultdict(lambda: [])
    bboxes = []
    for layer, bbox, tag in _render_mod_internal(mod):  # NOQA: F402
        tags[layer.replace(".", "_")].append(tag)
        bboxes.append(bbox)

    layer_key = lambda layer: (  # NOQA: E731, E501
        f"{LAYERS.index(layer):20d}" if layer in LAYERS else f"Z{layer}"
    )
    tags = [
        tag
        for layer in sorted(tags, key=layer_key, reverse=True)
        for tag in tags[layer]
    ]

    x1, y1, x2, y2 = add_bboxes(bboxes)
    xm, ym = max(abs(x1), abs(x2)), max(abs(y1), abs(y2))
    bounds = ((-xm, -ym), (xm, ym))
    return str(setup_svg(tags, bounds, margin=10))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("kicad_mod_file", type=Path)
    args = parser.parse_args()
    print(render_mod(args.kicad_mod_file.read_text()))
