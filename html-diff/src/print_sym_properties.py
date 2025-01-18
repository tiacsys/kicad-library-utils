#!/usr/bin/env python3

from xml.etree import ElementTree as ET

from html_util import (
    DiffProperty,
    PropertyType,
    make_count_table,
    make_property_diff_table,
)
from kicad_sym import KicadSymbol, Property


def _symbol_properties(old: KicadSymbol, new: KicadSymbol) -> list[DiffProperty]:

    leaf_props = [
        ["Name", "name"],
        ["Extends", "extends"],
    ]

    # These are properties that are on the root symbol, not the leaf symbols
    root_props = [
        ["Pin name offset", "pin_names_offset"],
        ["Pin names hidden", "hide_pin_names"],
        ["Pin numbers hidden", "hide_pin_numbers"],
        ["Is power symbol", "is_power"],
        ["Is in BOM", "in_bom"],
        ["Is on board", "on_board"],
        ["Number of units", "unit_count"],
        ["Number of styles", "demorgan_count"],
    ]

    properties = []

    for name, attr in leaf_props:
        old_val = getattr(old, attr) if old else None
        new_val = getattr(new, attr) if new else None
        properties.append(DiffProperty(name, old_val, new_val, PropertyType.NATIVE))

    old_root = old.get_root_symbol() if old else None
    new_root = new.get_root_symbol() if new else None

    for name, attr in root_props:
        old_val = getattr(old_root, attr) if old_root else None
        new_val = getattr(new_root, attr) if new_root else None
        properties.append(DiffProperty(name, old_val, new_val, PropertyType.NATIVE))

    # Gather the props in the old and new symbols
    old_props = set()
    new_props = set()

    if old:
        for prop in old.properties:
            old_props.add(prop.name)

    if new:
        for prop in new.properties:
            new_props.add(prop.name)

    for prop_name in old_props.union(new_props):

        old_prop_val: Property = None
        new_prop_val: Property = None

        if prop_name in old_props:
            old_prop_val = old.get_property(prop_name)
        if prop_name in new_props:
            new_prop_val = new.get_property(prop_name)

        prop_type = (
            PropertyType.DATASHEET if prop_name == "Datasheet" else PropertyType.FIELD
        )

        properties.append(
            DiffProperty(
                prop_name,
                old_prop_val.value if old_prop_val else None,
                new_prop_val.value if new_prop_val else None,
                prop_type,
            )
        )

    return properties


def _symbol_counts(
    old: KicadSymbol | None, new: KicadSymbol | None
) -> list[DiffProperty]:

    attrs = ["pins", "rectangles", "circles", "arcs", "polylines", "texts"]

    counts = []

    for attr in attrs:
        new_count = len(getattr(new, attr)) if new else 0
        old_count = len(getattr(old, attr)) if old else 0

        diff = DiffProperty(attr, old_count, new_count, PropertyType.NATIVE)

        counts.append(diff)

    return counts


def format_properties(old: KicadSymbol | None, new: KicadSymbol | None) -> str:

    properties = _symbol_properties(old, new)

    container = ET.Element("div")

    prop_table = make_property_diff_table(properties)
    container.append(prop_table)

    count_header = ET.Element("h4")
    count_header.text = "Primitive counts:"
    container.append(count_header)

    count_table = make_count_table(_symbol_counts(old, new))
    container.append(count_table)

    # Convert the XML container to a string
    out = ET.tostring(container, encoding="unicode", method="html")
    return out
