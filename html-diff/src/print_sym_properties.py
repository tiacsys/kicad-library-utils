#!/usr/bin/env python3

from pathlib import Path
import sys
from collections import defaultdict

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (common := Path(__file__).parent.parent.with_name('common').absolute()) not in sys.path:
        sys.path.insert(0, str(common))

from kicad_sym import KicadLibrary


def format_properties(lib_data, symbol_name):
    lib = KicadLibrary.from_file('<script>', data=lib_data)
    for sym in lib.symbols:
        if sym.name == symbol_name:
            break
    else:
        raise KeyError(f'Cannot find symbol {symbol_name} in library')

    out = '<table>\n'
    out += '  <tr><th>Name</th><th>Value</th></tr>\n'
    counts = defaultdict(lambda: 0)

    properties = {
        'Name': sym.name,
        'Pin name offset': sym.pin_names_offset,
        'Pin names hidden': sym.hide_pin_names,
        'Pin numbers hidden': sym.hide_pin_numbers,
        'Is power symbol': sym.is_power,
        'Is in BOM': sym.in_bom,
        'Is on board': sym.on_board,
        'Extends': sym.extends,
        'Number of units': sym.unit_count,
        'Number of styles': sym.demorgan_count}

    for k, v in properties.items():
        out += f'  <tr><td><strong>{k}</strong></td><td>{v}</td></tr>\n'

    for prop in sym.properties:
        out += f'  <tr><td><pre>{prop.name}</pre></td><td><pre>{prop.value}</pre></td></tr>\n'

    out += '</table>\n'
    out += '<h4>Primitive counts:</h4>\n'
    out += '<table>\n'
    out += '  <tr><th>Type</th><th>Count</th></tr>\n'

    counts = [(len(getattr(sym, attr)), attr.title())
              for attr in 'pins rectangles circles arcs polylines texts'.split()]

    # sort descending by count, then ascending alphabetically by name
    for count, name in sorted(counts, key=lambda e: (-e[0], e[1])):
        out += f'  <tr><td>{name}</td><td>{count}</td></tr>\n'

    out += '</table>'

    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('kicad_sym_file', type=Path)
    parser.add_argument('symbol_name')
    args = parser.parse_args()
    print(format_properties(args.kicad_sym_file.read_text(), args.symbol_name))
