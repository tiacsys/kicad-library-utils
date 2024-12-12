
import math
import textwrap


class Tag:
    """ Helper class to ease creation of SVG. All API functions that create SVG allow you to
    substitute this with your own implementation by passing a ``tag`` parameter. """

    def __init__(self, name, children=None, root=False, **attrs):
        self.name, self.attrs = name, attrs
        self.children = children or []
        self.root = root

    def __str__(self):
        prefix = '<?xml version="1.0" encoding="utf-8"?>\n' if self.root else ''
        opening = ' '.join([self.name] + [f'{key.replace("__", ":").replace("_", "-")}="{value}"'
                                          for key, value in self.attrs.items()])
        if self.children:
            children = '\n'.join(textwrap.indent(str(c), '  ') for c in self.children)
            return f'{prefix}<{opening}>\n{children}\n</{self.name}>'
        else:
            return f'{prefix}<{opening}/>'


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


def bbox(*args):
    xs, ys = [x for x, _ in args], [y for _, y in args]
    return min(xs), min(ys), max(xs), max(ys)


def add_bboxes(bboxes):
    # format: [(min_x, min_y, max_x, max_Y), ...]
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')

    for x1, y1, x2, y2 in bboxes:
        assert x1 <= x2 and y1 <= y2
        if x1 < min_x:
            min_x = x1
        if y1 < min_y:
            min_y = y1
        if x2 > max_x:
            max_x = x2
        if y2 > max_y:
            max_y = y2

    return min_x, min_y, max_x, max_y


def svg_rotation(angle_rad, cx=0, cy=0):
    return f'rotate({float(math.degrees(angle_rad)):.4} {float(cx):.6} {float(cy):.6})'


def setup_svg(tags, bounds, margin=0, pagecolor='white', tag=Tag, inkscape=False):
    (min_x, min_y), (max_x, max_y) = bounds

    if margin:
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin

    w, h = max_x - min_x, max_y - min_y
    w = 1.0 if math.isclose(w, 0.0) else w
    h = 1.0 if math.isclose(h, 0.0) else h

    if inkscape:
        tags.insert(0, tag('sodipodi:namedview', [], id='namedview1', pagecolor=pagecolor,
                           inkscape__document_units='mm'))
        namespaces = dict(
            xmlns="http://www.w3.org/2000/svg",
            xmlns__xlink="http://www.w3.org/1999/xlink",
            xmlns__sodipodi='http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
            xmlns__inkscape='http://www.inkscape.org/namespaces/inkscape')

    else:
        namespaces = dict(
            xmlns="http://www.w3.org/2000/svg",
            xmlns__xlink="http://www.w3.org/1999/xlink")

    # TODO export apertures as <uses> where reasonable.
    return tag('svg', tags,
               width=f'{w}mm', height=f'{h}mm',
               viewBox=f'{min_x} {min_y} {w} {h}',
               **namespaces,
               root=True)
