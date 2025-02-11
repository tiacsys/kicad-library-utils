#!/usr/bin/env python3

import enum

from kicad_sym import KicadSymbol, Property


class PropertyType(enum.Enum):
    """
    This drives how we might want to display a property in the table.
    """

    # Text field dat
    FIELD = enum.auto()
    # DS URL
    DATASHEET = enum.auto()
    # Some "internal" data not directly entered as strings
    NATIVE = enum.auto()


class DiffProperty:
    """
    Class that represents some property of a symbol that night change.
    """

    old: str | None
    new: str | None
    prop_type: PropertyType

    def __init__(
        self, name: str, old: str | None, new: str | None, prop_type: PropertyType
    ):
        """
        :param name: The name of the property
        :param old: The old value of the property, or none if the old property is not present
        :param new: The new value of the property, or none if the new property is not present
        :param prop_type: The type of the property
        """

        self._old = old
        self._new = new

        self.name = name
        self.prop_type = prop_type

    @property
    def old(self) -> str:
        return self._old if self._old is not None else ""

    @property
    def new(self) -> str:
        return self._new if self._new is not None else ""


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


def _symbol_counts(old, new) -> list[DiffProperty]:

    attrs = ["pins", "rectangles", "circles", "arcs", "polylines", "texts"]

    counts = []

    for attr in attrs:
        new_count = len(getattr(new, attr)) if new else 0
        old_count = len(getattr(old, attr)) if old else 0

        diff = DiffProperty(attr, old_count, new_count, PropertyType.NATIVE)

        counts.append(diff)

    return counts


def format_properties(old: KicadSymbol | None, new: KicadSymbol | None) -> str:

    out = "<table>\n"
    out += "  <tr><th>Name</th><th>Old Value</th><th>New Value</th></tr>\n"

    properties = _symbol_properties(old, new)

    def cell(val, cls: str | None, inner_tag: str | None = None):

        if inner_tag:
            if inner_tag == "a":
                val = f'<a target="_blank" href="{val}">{val}</a>'
            else:
                val = f"<{inner_tag}>{val}</{inner_tag}>"

        c = "    <td"
        if cls:
            c += f' class="{cls}"'

        c += f">{val}</td>\n"
        return c

    for prop in properties:

        cls = None
        if prop.old == prop.new:
            cls = "prop-same"

        out += "  <tr>\n"
        if prop.prop_type == PropertyType.DATASHEET:
            out += cell(prop.name, None, "pre")
            out += cell(prop.old, cls, "a")
            out += cell(prop.new, cls, "a")

        elif prop.prop_type == PropertyType.FIELD:
            out += cell(prop.name, None, "pre")
            out += cell(prop.old, cls, "pre")
            out += cell(prop.new, cls, "pre")

        elif prop.prop_type == PropertyType.NATIVE:
            out += cell(prop.name, None, "strong")
            out += cell(prop.old, cls)
            out += cell(prop.new, cls)
        else:
            raise ValueError(f"Unknown property type {prop.prop_type}")

        out += "  </tr>\n"

    out += "</table>\n"
    out += "<h4>Primitive counts:</h4>\n"
    out += "<table>\n"
    out += "  <tr><th>Type</th><th>Old count</th><th>New count</th></tr>\n"

    counts = _symbol_counts(old, new)

    # sort descending by count, then ascending alphabetically by name
    for count_diff in sorted(counts, key=lambda d: (-d.new, d.name)):

        cls = "prop-same" if count_diff.old == count_diff.new else None

        out += "  <tr>\n"
        out += cell(count_diff.name, None, "strong")
        out += cell(count_diff.old, cls)
        out += cell(count_diff.new, cls)

    out += "</table>"

    return out
