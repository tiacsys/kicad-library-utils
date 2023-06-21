#!/usr/bin/env python3

import math
import re
import sys
from pathlib import Path

try:
    import kicad_sym
except ImportError:
    if (common := Path(__file__).parent.parent.with_name('common').absolute()) not in sys.path:
        sys.path.insert(0, str(common))

import kicad_sym  # NOQA: F811
from svg_util import Tag, setup_svg, bbox, add_bboxes


def elem_style(elem):
    if isinstance(elem, (kicad_sym.Property, kicad_sym.Text)):
        return {'class': 'l-any-f'}
    else:
        classes = 'l-any-s'
        if getattr(elem, 'fill_type', None) == 'outline':
            classes += ' l-any-f'

        return {'class': classes,
                'stroke_width': max(0.2, getattr(elem, 'stroke_width', 0)),
                'stroke_linecap': 'round',
                'stroke_linejoin': 'round'}


def render_rect(elem, **style):
    x, y = min(elem.startx, elem.endx), min(-elem.starty, -elem.endy)
    w, h = max(elem.startx, elem.endx)-x, max(-elem.starty, -elem.endy)-y
    yield (x, y, x+w, y+h), Tag('rect', **style, x=x, y=y, width=w, height=h)


def render_circle(elem, **style):
    x, y = elem.centerx, -elem.centery
    r = max(0.2, elem.radius)
    yield (x-r, y-r, x+r, y+r), Tag('circle', **style, cx=x, cy=y, r=r)


def render_polyline(elem, **style):
    points = [(pt.x, -pt.y) for pt in elem.points]
    path_data = 'M ' + ' L '.join(f'{x:.6f} {y:.6f}' for x, y in points)
    yield bbox(*points), Tag('path', **style, d=path_data)


def distance_between(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


# https://stackoverflow.com/questions/28910718/give-3-points-and-a-plot-circle
def define_circle(p1, p2, p3):
    """
    Returns the center and radius of the circle passing the given 3 points.
    In case the 3 points form a line, raises a ValueError.
    """

    temp = p2[0] * p2[0] + p2[1] * p2[1]
    bc = (p1[0] * p1[0] + p1[1] * p1[1] - temp) / 2
    cd = (temp - p3[0] * p3[0] - p3[1] * p3[1]) / 2
    det = (p1[0] - p2[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p2[1])

    if abs(det) < 1.0e-6:
        # could be three points very, very close or co-incident
        if distance_between(p2, p1) < 1.0e-6 and distance_between(p3, p2) < 1.0e-6:
            # zero sized, centre on midpoint (though any point would do as they're so close)
            return ((p2[0], p2[0]), 0)

        # otherwise they're far apart but in a line
        raise ValueError(f'Attempted to define a circle by 3 collinear points: {p1}, {p2}, {p3}')

    # Center of circle
    cx = (bc*(p2[1] - p3[1]) - cd*(p1[1] - p2[1])) / det
    cy = ((p1[0] - p2[0]) * cd - (p2[0] - p3[0]) * bc) / det

    radius = math.sqrt((cx - p1[0])**2 + (cy - p1[1])**2)
    return ((cx, cy), radius)


def render_arc(arc, **style):
    x1, y1 = arc.startx, -arc.starty
    x2, y2 = arc.endx, -arc.endy
    (cx, cy), r = define_circle((x1, y1), (arc.midx, -arc.midy), (x2, y2))

    x1r = x1 - cx
    y1r = y1 - cy
    x2r = x2 - cx
    y2r = y2 - cy
    a1 = math.atan2(x1r, y1r)
    a2 = math.atan2(x2r, y2r)
    da = (a2 - a1 + math.pi) % (2*math.pi) - math.pi

    large_arc = int(da > math.pi)
    d = f'M {x1:.6f} {y1:.6f} A {r:.6f} {r:.6f} 0 {large_arc} 0 {x2:.6f} {y2:.6f}'
    # We just approximate the bbox here with that of a circle. Calculating precise arc bboxes is
    # hairy, and unnecessary for our purposes.
    yield (cx-r, cy-r, cx+r, cy+r), Tag('path', **style, d=d)


def render_text(elem, **style):
    content = getattr(elem, 'text', getattr(elem, 'value', None))
    assert content is not None
    x, y = elem.posx, -elem.posy

    yield from text_elem(x, y, elem.rotation, content, elem.effects, style)


def text_elem(x, y, rot, content, effects, style):
    if rot in (90, 270):
        xform = {'transform': f'rotate({-rot} {x} {y})'}
    else:
        xform = {}

    size = 1.27
    anchor = 'middle'
    style_extra = {}

    if effects is not None:
        if effects.is_hidden:
            return

        size = effects.sizey/2 or 1.27
        anchor = {
            'center': 'middle',
            'left': 'start',
            'right': 'end'}.get(effects.h_justify, 'middle')
        baseline = {
            'top': 'text-top',
            'center': 'middle',
            'bottom': 'hangign'}.get(effects.v_justify, 'middle')

    content = re.sub(
        r'~{([^}]*)}|^~([^{].*)$', r'<tspan text-decoration="overline">\1\2</tspan>',
        content)
    content = re.sub(
        r'_{([^}]*)}', r'<tspan font-size="70%" baseline-shift="sub">\1</tspan>',
        content)

    yield (x, y, x, y), Tag('text', [content], font_family='monospace',
                            font_size=f'{size*0.7:.3f}mm', x=x, y=y, dominant_baseline=baseline,
                            text_anchor=anchor, **style, **xform, **style_extra)


def render_pin(elem, **style):
    if elem.is_hidden:
        return

    l = elem.length  # NOQA: E741
    x1, y1 = elem.posx, -elem.posy
    x2, y2 = x1 + l, y1
    rot = elem.rotation
    xform = {'transform': f'rotate({-rot} {x1} {y1})'}

    yield bbox((x1, y1), (x2, y2)), Tag('path', **xform, **style,
                                        d=f'M {x1:.6f} {y1:.6f} L {x2:.6f} {y2:.6f}')

    eps = 1
    for tag in {
            'line': [],
            'inverted': [
                Tag('circle', **xform, **style, cx=x2-eps/3-0.2, cy=y2, r=eps/3)],
            'clock': [
                Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],  # NOQA: E501
            'inverted_clock': [
                Tag('circle', **xform, **style, cx=x2-eps/3-0.2, cy=y2, r=eps/3),
                Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],  # NOQA: E501
            'input_low': [
                Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}')],  # NOQA: E501
            'clock_low': [
                Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}'),  # NOQA: E501
                Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],  # NOQA: E501
            'output_low': [
                Tag('path', **xform, **style, d=f'M {x2} {y2-eps} L {x2-eps} {y2}')],  # NOQA: E501
            'edge_clock_high': [
                Tag('path', **xform, **style, d=f'M {x2} {y2} L {x2-eps} {y2-eps} L {x2-eps} {y2}'),  # NOQA: E501
                Tag('path', **xform, **style, d=f'M {x2} {y2-eps/2} L {x2+eps/2} {y2} L {x2} {y2+eps/2}')],  # NOQA: E501
            'non_logic': [
                Tag('path', **xform, **style, d=f'M {x2-eps/2} {y2-eps/2} L {x2+eps/2} {y2+eps/2}'),  # NOQA: E501
                Tag('path', **xform, **style, d=f'M {x2-eps/2} {y2+eps/2} L {x2+eps/2} {y2-eps/2}')],  # NOQA: E501
            # FIXME...
    }.get(elem.shape, []):
        yield (x1, y1, x1, y1), tag

    if rot in (90, 270):
        t_rot = 90
    else:
        t_rot = 0

    elem.name_effect.h_justify = 'left'
    if rot in (180, 270):
        elem.name_effect.h_justify = {
            'left': 'right',
            'right': 'left'
        }.get(elem.name_effect.h_justify)

    k = 0.4
    e = l + k
    nx, ny = {
        0: (x1+e, y1),
        90: (x1, y1-e),
        180: (x1-e, y1),
        270: (x1, y1+e), }[rot]
    yield from text_elem(nx, ny, t_rot, elem.name, elem.name_effect, {'class': 'l-any-f'})

    elem.number_effect.v_justify = 'top'
    nx, ny = {
        0: (x1+l/2, y1-k),
        90: (x1-k, y1-l/2),
        180: (x1-l/2, y1-k),
        270: (x1-k, y1+l/2), }[rot]
    yield from text_elem(nx, ny, t_rot, elem.number, elem.number_effect, {'class': 'l-any-f'})


def _render_sym_internal(sym, unit=1):
    for fun, elems in [
            (render_rect, sym.rectangles),
            (render_circle, sym.circles),
            (render_polyline, sym.polylines),
            (render_arc, sym.arcs),
            (render_pin, sym.pins),
            (render_text, sym.texts),
            (render_text, sym.properties)]:
        for elem in elems:
            if not hasattr(elem, 'unit') or elem.unit in (0, unit):  # bad API
                for bbox, tag in fun(elem, **elem_style(elem)):  # NOQA: F402
                    yield bbox, tag


def render_sym(data, name, default_style=True):
    if not data:
        return

    lib = kicad_sym.KicadLibrary.from_file('<command line>', data=data)
    for sym in lib.symbols:
        if sym.name == name:
            break
    else:
        raise KeyError(f'Symbol "{name}" not found in library.')

    for unit in range(1, sym.unit_count+1):
        tags, bboxes = [], []

        for bbox, tag in _render_sym_internal(sym, unit):  # NOQA: F402
            tags.append(tag)
            bboxes.append(bbox)

        x1, y1, x2, y2 = add_bboxes(bboxes)
        xm, ym = max(abs(x1), abs(x2)), max(abs(y1), abs(y2))
        bounds = ((-xm, -ym), (xm, ym))
        if default_style:
            tags.insert(0, Tag('style', ['''
                .l-any-f { fill: black; }
                .l-any-s { stroke: black }
                * { fill: none; stroke: none }
                tspan { fill: black; } ''']))
        yield str(setup_svg(tags, bounds, margin=10))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('kicad_sym_file', type=Path)
    args = parser.parse_args()
    _suffix, _, sym_name = args.kicad_sym_file.suffix.partition(':')
    libfile = args.kicad_sym_file.with_suffix('.kicad_sym')
    for i, unit_data in enumerate(render_sym(libfile.read_text(), sym_name)):
        outf = args.kicad_sym_file.parent / f'{args.kicad_sym_file.stem}_{sym_name}_{i}.svg'
        print(f'writing unit {i} to {str(outf)}', file=sys.stderr)
        outf.write_text(unit_data)
