"""
HTML utility functions for html-diff
"""

import enum
from xml.etree import ElementTree as ET


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


def heading(tag: str, text: str) -> ET.Element:
    """
    Create a heading element with the given tag and text.
    """

    elem = ET.Element(tag)
    elem.text = text

    return elem


def header_row(entries: list[str]) -> ET.Element:

    row = ET.Element("tr")
    for entry in entries:
        cell = ET.Element("th")
        cell.text = entry
        row.append(cell)

    return row


def diff_cell(val: str, cls: str | None, inner_tag: str | None = None) -> ET.Element:

    val = str(val) if val is not None else ""

    cell = ET.Element("td")
    if cls:
        cell.set("class", cls)

    if inner_tag is None:
        cell.text = val
    else:
        if inner_tag == "a":
            inner = ET.Element("a")
            inner.text = val
            inner.set("target", "_blank")
            inner.set("href", val)
        else:
            inner = ET.Element(inner_tag)
            inner.text = val
        cell.append(inner)

    return cell


def make_property_diff_table(properties: list[DiffProperty]) -> ET.Element:

    table = ET.Element("table")
    table.append(header_row(["Name", "Old Value", "New Value"]))

    for prop in properties:

        row = ET.Element("tr")

        cls = None
        if prop.old == prop.new:
            cls = "prop-same"

        if prop.prop_type == PropertyType.DATASHEET:
            row.append(diff_cell(prop.name, None, "strong"))
            row.append(diff_cell(prop.old, cls, "a"))
            row.append(diff_cell(prop.new, cls, "a"))

        elif prop.prop_type == PropertyType.FIELD:
            row.append(diff_cell(prop.name, None, "pre"))
            row.append(diff_cell(prop.old, cls, "pre"))
            row.append(diff_cell(prop.new, cls, "pre"))

        elif prop.prop_type == PropertyType.NATIVE:
            row.append(diff_cell(prop.name, None, "strong"))
            row.append(diff_cell(prop.old, cls))
            row.append(diff_cell(prop.new, cls))
        else:
            raise ValueError(f"Unknown property type {prop.prop_type}")

        table.append(row)

    return table


def make_count_table(counts: list[DiffProperty]) -> ET.Element:

    table = ET.Element("table")
    table.append(header_row(["Type", "Old Count", "New Count"]))

    for count in counts:

        cls = "prop-same" if count.old == count.new else None

        row = ET.Element("tr")
        row.append(diff_cell(count.name, None, "strong"))
        row.append(diff_cell(str(count.old), cls))
        row.append(diff_cell(str(count.new), cls))

        table.append(row)

    return table
