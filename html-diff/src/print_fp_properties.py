#!/usr/bin/env python3

import sys
from collections import defaultdict
from pathlib import Path

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (
        common := Path(__file__).parent.parent.with_name("common").absolute()
    ) not in sys.path:
        sys.path.insert(0, str(common))

from kicad_mod import KicadMod


def lookup(l, k, default=None):  # NOQA: 741
    for elem in l:
        if isinstance(elem, list) and len(elem) > 1:
            if elem[0] == k:
                return elem[1:]
    return default


def format_properties(data):
    mod = KicadMod(data=data)
    out = "<table>\n"
    out += "  <tr><th>Name</th><th>Value</th></tr>\n"
    counts = defaultdict(lambda: 0)
    _module, _name, *mod = mod.sexpr_data
    for tag, *values in mod:
        counts[tag] += 1
        # Exclude graphical primitives
        if tag in ("fp_line", "fp_rect", "fp_circle", "fp_poly", "pad", "zone"):
            continue

        if tag == "fp_text":
            tag = f"fp_text <pre>{values[0]}</pre>"
            x, y, *_ignored = lookup(values, "at", ("?", "?"))
            layer = lookup(values, "layer", "?")
            value = f'at ({x}, {y}), layers {", ".join(layer)} <pre>{values[1]}</pre>'
        elif tag == "model":
            value = f"<pre>{values[0]}</pre>"
        else:
            value = "<pre>" + "\n".join(map(str, values)) + "</pre>"

        out += f"  <tr><td>{tag}</td><td>{value}</td></tr>\n"

    out += "</table>\n"
    out += "<h4>Item counts:</h4>\n"
    out += "<table>\n"
    out += "  <tr><th>Type</th><th>Count</th></tr>\n"

    # "-count" hack to sort by count descending, but tag alphabetically ascending
    for count, tag in sorted((-count, tag) for tag, count in counts.items()):
        out += f"  <tr><td>{tag}</td><td>{-count}</td></tr>\n"

    out += "</table>"

    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("kicad_mod_file", type=Path)
    args = parser.parse_args()
    print(format_properties(args.kicad_mod_file.read_text()))
