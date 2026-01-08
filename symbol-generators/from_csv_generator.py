#!/usr/bin/env python3

# Generator that creates a symbol from a pinout CSV.
# See ./template.csv and ./BQ24004-example.csv for reference.

# add directory (common) that contains the kicad_sym lib to the path
# you can also use a relative module path instead
import os
import sys

# workaround to import the kicad_sym library
common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, "common")
)
if common not in sys.path:
    sys.path.insert(0, common)

import argparse
import csv
import math
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Dict, List, Tuple

from kicad_sym import AltFunction, KicadLibrary, KicadSymbol, Pin, Rectangle, mil_to_mm

# Parser wide constants
CHAR_WIDTH_GUESSTIMATE = 50
PIN_NAME_LIMIT = 12


# Parser specific type definitions
class Metadata:
    """
    The metadata of the symbol to generate.
    """

    reference: str
    name: str
    footprint: str | None
    footprint_filter: str | None
    datasheet: str | None
    description: str | None
    keywords: str | None

    def __init__(self, data: dict):
        if type(data) is not dict:
            raise TypeError("Parameter data must be of type dict.")
        if "reference" not in data or "name" not in data:
            raise ValueError(
                "The required keys 'reference' and/or 'name' are missing in the data."
            )
        self.reference = data.get("reference", "")
        self.name = data.get("name", "")
        self.footprint = data.get("footprint")
        self.footprint_filter = data.get("footprint_filter")
        self.datasheet = data.get("datasheet")
        self.description = data.get("description")
        self.keywords = data.get("keywords")

    def __str__(self):
        string_rep = f"{self.reference} '{self.name}':\n"
        string_rep += f"\tfootprint: {self.footprint}\n"
        string_rep += f"\tfootprint_filter: {self.footprint_filter}\n"
        string_rep += f"\tdatasheet: {self.datasheet}\n"
        string_rep += f"\tdescription: {self.description}\n"
        string_rep += f"\tkeywords: {self.keywords}\n"
        return string_rep

    def __repr__(self):
        return f"{self.reference} '{self.name}'"


class PinData:
    """
    The data for one symbol pin to generate.
    """

    class Side(StrEnum):
        """
        All valid sides a pin can have.
        """

        TOP = "top"
        BOTTOM = "bottom"
        LEFT = "left"
        RIGHT = "right"

    pin_number: int | None
    name: str
    alt_names: List[str]
    type: str
    side: Side
    unit: str | None

    def __init__(self, data: dict, split_pin_names: int | None = None):
        if type(data) is not dict:
            raise TypeError("Parameter data must be of type dict.")

        self.type = data.get("type", "").lower().replace(" ", "_")

        if self.type != "space" and "pin" not in data:
            raise ValueError("Missing pin number in data")
        if self.type != "space" and "name" not in data:
            raise ValueError("Missing pin name in data")

        if "pin" in data and len(data["pin"].strip()) > 0:
            self.pin_number = int(data["pin"])
        else:
            self.pin_number = None

        if split_pin_names is not None:
            pin_names = list(map(str.strip, data.get("name", "").split("/")))
            split_index = max(split_pin_names, 1)
            self.name = "/".join(pin_names[:split_index])
            self.alt_names = pin_names[split_index:]
        else:
            self.name = data.get("name", "")
            self.alt_names = []

        if len(self.name) > PIN_NAME_LIMIT:
            print(
                f"warning: pin name '{self.name}' is longer than {PIN_NAME_LIMIT} characters"
            )

        self.side = PinData.Side(data["side"].lower().replace(" ", "_"))
        if not self.side:
            self.side = PinData.Side.RIGHT

        self.unit = data.get("unit", "").strip()

    def __str__(self):
        return (
            f"<({self.pin_number or ''}) '{self.name}':"
            + f" side: {self.side.value}, type: {self.type}, unit: {self.unit}>"
        )

    def __repr__(self):
        return self.__str__()


# disable flake8 error here as CIs flake8 version is to old to properly handle PEP 613 – Explicit Type Aliases
type PinStack = List[PinData]  # noqa: E999


# function definitions used by this parser:


# parse input CSV
def parse_csv(
    filename: str, split_pin_names: int | None = None
) -> Tuple[Metadata, List[PinData]]:
    """Parses the given CSV file into a list of pins and metadata.

    Parameters:
        filename (str): The path to the CSV file to parse.
        split_pin_names (int | None): If and how often to split pin names into alt names by '/'.

    Returns:
        tuple: A tuple with the symbol metadata as a dict as the first element
               and a list of pin data as the second element.
    """
    metadata_dict: Dict[str, str] = {}
    metadata: Metadata | None = None
    in_metadata_section: bool = True

    pin_headers: List[str] | None = None
    pin_data: List[PinData] = []

    with open(filename, newline="") as csvfile:
        reader = csv.reader(
            filter(lambda row: not row.startswith("# "), csvfile)
        )  # filter out lines with comments
        for row in reader:
            if in_metadata_section:  # parse metadata
                if (
                    len(row) == 0 or len(row[0].strip()) == 0
                ):  # skip from metadata to pin data on first empty line
                    in_metadata_section = False

                    try:
                        metadata = Metadata(metadata_dict)
                        if not metadata.footprint:
                            print('warning: key "footprint" is missing in the metadata')
                        if not metadata.footprint_filter:
                            print(
                                'warning: key "footprint_filter" is missing in the metadata'
                            )
                        if not metadata.datasheet:
                            print('warning: key "datasheet" is missing in the metadata')
                        if not metadata.description:
                            print(
                                'warning: key "description" is missing in the metadata'
                            )
                        if not metadata.keywords:
                            print('warning: key "keywords" is missing in the metadata')
                    except ValueError as e:
                        if "reference" not in metadata_dict.keys():
                            print('error: key "reference" is missing in the metadata')
                        if "name" not in metadata_dict.keys():
                            print('error: key "name" is missing in the metadata')
                        raise e

                    continue
                else:  # add row to metadata
                    metadata_key = row[0].lower().replace(" ", "_")
                    metadata_value = row[1]
                    if metadata_key not in metadata_dict:
                        if len(metadata_value) > 0:
                            metadata_dict[metadata_key] = metadata_value
                    else:
                        raise ValueError(
                            f'metadata key "{metadata_key}" defined multiple times'
                        )
            else:  # parse pin data
                if len(row) == 0 or all(
                    map(lambda cell: cell == "", row)
                ):  # skip empty rows
                    continue
                elif (
                    pin_headers is None
                ):  # treat first pin data row as header names/order
                    pin_headers = list(
                        map(lambda h: h.lower(), filter(lambda h: len(h) > 0, row))
                    )

                    required_key_missing = False
                    if "pin" not in pin_headers:
                        print('error: key "pin" is missing in the header row')
                        required_key_missing = True
                    if "name" not in pin_headers:
                        print('error: key "name" is missing in the header row')
                        required_key_missing = True
                    if "type" not in pin_headers:
                        print('error: key "type" is missing in the header row')
                        required_key_missing = True
                    if "side" not in pin_headers:
                        print('warning: key "side" is missing in the header row')
                    if required_key_missing:
                        raise ValueError(
                            "A required key is missing in the CSV pin header row."
                        )
                else:
                    parsed_pin_data = {}

                    for column, header in enumerate(pin_headers):
                        if column >= len(row):
                            break
                        parsed_pin_data[header] = row[column]

                    if "unit" in pin_headers and parsed_pin_data["unit"].strip() == "":
                        print(
                            f'warning: no unit set for pin {parsed_pin_data["pin"]} "{parsed_pin_data["name"]}"'
                        )

                    if parsed_pin_data["pin"].strip() == "":
                        pin_data.append(PinData(parsed_pin_data, split_pin_names))
                    else:
                        for pin_num_str in parsed_pin_data["pin"].split(","):
                            pin_range_arr = pin_num_str.split("-", maxsplit=1)
                            pin_range_start = int(pin_range_arr[0].strip())
                            pin_range_end = (
                                int(pin_range_arr[1].strip())
                                if len(pin_range_arr) > 1
                                else pin_range_start
                            )
                            pin_range = range(pin_range_start, pin_range_end + 1)
                            for pin_num in pin_range:
                                new_pin = parsed_pin_data.copy()
                                new_pin["pin"] = str(pin_num)
                                pin_data.append(PinData(new_pin, split_pin_names))

    if metadata is None:
        raise ValueError("Failed to parse metadata from CSV.")
    return (metadata, pin_data)


# group pins by unit name
def group_pins_by_unit(pin_data: List[PinData]) -> Dict[str, List[PinData]]:
    """Groups together the given pins by their unit.

    Parameters:
        pin_data (list): A list of pin data.

    Returns:
        dict: A dict mapping for each unit the name of the unit to list of pins on in this unit.
    """
    symbol_units = defaultdict(list)
    for pin in pin_data:
        symbol_units[pin.unit].append(pin)
    return dict(symbol_units)


# group pins according to side
def group_pins_by_side(pins: List[PinData]) -> Dict[PinData.Side, List[PinData]]:
    """Groups together the given pins by their side.

    Parameters:
        pins (list): A list of pin data.

    Returns:
        dict: A dict mapping for each side the name of the side to list of pins on this side.
    """
    side_dict = {}
    for side in PinData.Side:
        side_dict[side] = []
    for pin in pins:
        side_dict[pin.side].append(pin)
    return side_dict


def create_pin_stacks(pins: List[PinData]) -> List[PinStack]:
    """Groups together the given pins by their name to create stacks of same pins.

    Parameters:
        pins (list): A list of pin data.

    Returns:
        list: A list of lists each containing a group of pins with the same name.
    """
    # mapping of pin names to pin pin_stacks
    pin_stacks: Dict[str, List[PinData]] = OrderedDict()
    # go through all pins and sort them into pin_stacks
    for index, pin in enumerate(pins):
        # do not group spaces and no_connects
        if pin.type == "space" or pin.type == "no_connect":
            pin_stacks[f"do_not_group_{index}"] = [pin]
        # add pins to existing pin_stacks
        elif pin.name in pin_stacks:
            pin_stacks[pin.name].append(pin)
        # create new pin_stacks for new pin names
        else:
            pin_stacks[pin.name] = [pin]
    # return list of pin stacks where the pins in each stack are sorted by pin number
    return list(
        map(lambda g: sorted(g, key=lambda p: p.pin_number), pin_stacks.values())
    )


def pos_for_pin(pin_count: int, index: int, direction: bool = True) -> int:
    """Calculates the position for the pin at the given index.

    Parameters:
        pin_count (int): The total number of pins on the axis to calculate the position for.
        index (int): The index of the pin to calculate the position for.
        direction (bool): Whether the highest pin is on the positive (True) or negative side (False) of the axis.

    Returns:
        int: The position of the pin at the given index.
    """
    dir_int = 1 if direction else -1
    return (-dir_int * (pin_count // 2) * 100) + (dir_int * index * 100)


def pin_label_width(pin: PinData) -> int:
    """Calculates the estimated width of the label of the given pin.

    Parameters:
        pin (PinData): The pin data to calculate the label width for.

    Returns:
        int: The estimated width of the pin's label.
    """
    return (len(pin.name) + 1) * CHAR_WIDTH_GUESSTIMATE


def calculate_base_bounding_box_size(
    pin_stacks: Dict[PinData.Side, List[PinStack]],
) -> Tuple[int, int]:
    """Calculates the base bounding box containing the given pin stacks for each side.

    Parameters:
        pin_stacks (dict): The pin stacks for each side to calculate the base bounding box for.

    Returns:
        tuple: The base bounding box as a tuple of width, height.
    """

    pin_count_horizontal = max(
        len(pin_stacks[PinData.Side.TOP]), len(pin_stacks[PinData.Side.BOTTOM])
    )
    pin_count_vertical = max(
        len(pin_stacks[PinData.Side.LEFT]), len(pin_stacks[PinData.Side.RIGHT])
    )

    total_horizontal_pin_width = (pin_count_horizontal + 1) * 100
    max_pin_name_length_left = max(
        (pin_label_width(pin) for pin, *others in pin_stacks[PinData.Side.LEFT]),
        default=0,
    )
    max_pin_name_length_right = max(
        (pin_label_width(pin) for pin, *others in pin_stacks[PinData.Side.RIGHT]),
        default=0,
    )

    bounding_box_width = (
        max(
            total_horizontal_pin_width,
            max_pin_name_length_left,
            max_pin_name_length_right,
            200,
        )
        // 200
        + 1
    ) * 200

    total_vertical_pin_width = (pin_count_vertical + 1) * 100
    max_pin_name_length_top = max(
        (pin_label_width(pin) for pin, *others in pin_stacks[PinData.Side.TOP]),
        default=0,
    )
    max_pin_name_length_bottom = max(
        (pin_label_width(pin) for pin, *others in pin_stacks[PinData.Side.BOTTOM]),
        default=0,
    )

    bounding_box_height = (
        max(
            total_vertical_pin_width,
            max_pin_name_length_top,
            max_pin_name_length_bottom,
            200,
        )
        // 200
        + 1
    ) * 200

    return (bounding_box_width, bounding_box_height)


def check_label_intersection(
    pin_stacks: List[PinStack],
    pin_stacks_opposite: List[PinStack],
    current_bounding_box: Tuple[int, int],
    pin_length: int,
) -> bool:
    """Checks if the labels of the given pin_stacks intersect with the labels of the opposite side.

    Parameters:
        pin_stacks (list): A list of pin stacks to check the intersection of labels for.
        pin_stacks_opposite (list): The list of pin stacks on the opposite side.
        current_bounding_box (tuple): The width and height of the current bounding box.
        pin_length (int): The pin length according to KLC S4.1.

    Returns:
        bool: Whether the labels of pin_stacks intersect with the labels of the opposite side or not.
    """
    b_width, b_height = current_bounding_box
    # Check intersection for all given pin stacks
    for i, pin_stack in enumerate(pin_stacks):
        pin = pin_stack[
            0
        ]  # Use first pin in stack as pin stacks are grouped by label/name
        length = pin_label_width(pin)
        x_pos = pos_for_pin(len(pin_stacks), i, True)
        y_pos = -b_height / 2 - pin_length

        # Check intersection with each pin stack on the opposite side
        for j, pin_stack_opposite in enumerate(pin_stacks_opposite):
            pin_opposite = pin_stack_opposite[0]
            length_opposite = pin_label_width(pin_opposite)
            x_pos_opposite = pos_for_pin(len(pin_stack_opposite), j, True)
            y_pos_opposite = b_height / 2 + pin_length

            # Check intersection of the two labels
            if (
                x_pos_opposite < x_pos + 100
                and x_pos_opposite + 100 > x_pos
                and y_pos + length > y_pos_opposite - length_opposite - 50
            ):
                return True  # Return if one pair of labels intersect

    return False


def extend_bounding_box(
    pin_stacks: Dict[PinData.Side, List[PinStack]],
    bounding_box: Tuple[int, int],
    pin_length: int,
    min_aspect_ratio: float,
) -> Tuple[int, int]:
    """Extends a given bounding box until no pin stack labels overlap anymore.

    Parameters:
        pin_stacks (list): The list of pin stacks to check and remove intersections for.
        bounding_box (tuple): A tuple of the bounding box width and height.
        pin_length (int): The pin length according to KLC S4.1 for this symbol.
        min_aspect_ratio (float): The min aspect ratio to enforce while calculating.

    Returns:
        tuple: The extended bounding box as a tuple of width and height.
    """
    bounding_box_width, bounding_box_height = bounding_box

    # Extend bounding box size until no pin labels intersect
    intersect_top = True
    intersect_bottom = True
    intersect_left = True
    intersect_right = True

    while intersect_top or intersect_bottom or intersect_left or intersect_right:

        intersect_top = check_label_intersection(
            pin_stacks[PinData.Side.TOP],
            pin_stacks[PinData.Side.BOTTOM],
            (bounding_box_width, bounding_box_height),
            pin_length,
        )

        intersect_bottom = check_label_intersection(
            pin_stacks[PinData.Side.BOTTOM],
            pin_stacks[PinData.Side.TOP],
            (bounding_box_width, bounding_box_height),
            pin_length,
        )

        if intersect_top or intersect_bottom:
            bounding_box_height += 200

        intersect_left = check_label_intersection(
            pin_stacks[PinData.Side.LEFT],
            pin_stacks[PinData.Side.RIGHT],
            (bounding_box_height, bounding_box_width),
            pin_length,
        )

        intersect_right = check_label_intersection(
            pin_stacks[PinData.Side.RIGHT],
            pin_stacks[PinData.Side.LEFT],
            (bounding_box_height, bounding_box_width),
            pin_length,
        )

        if intersect_left or intersect_right:
            bounding_box_width += 200

    if (
        min_aspect_ratio is not None
        and bounding_box_width / bounding_box_height < min_aspect_ratio
    ):
        bounding_box_width = int(
            math.ceil(bounding_box_height * min_aspect_ratio / 200.0) * 200
        )

    return (bounding_box_width, bounding_box_height)


def generate_pins(
    pin_stacks: List[PinStack],
    posx_func: Callable[[int], int],
    posy_func: Callable[[int], int],
    rotation: int,
    pin_length: int,
    unit_index: int,
) -> None:
    """Adds the given pin stacks to the new symbol using the given functions and rotation to determine pin positions.

    Parameters:
        pin_stacks (list): The list of pin stacks to place where each is a list of pins.
        posx_func (func): Function returning the x position of a pin (stack) for a given index.
        posy_func (func): Function returning the y position of a pin (stack) for a given index.
        rotation (int): The rotation/orientation of the pins.
        pin_length (int): The pin length according to KLC S4.1
        unit_index (int): The index of the unit inside of the symbol to generate the pins in.
    """
    # Add all given pin stacks to the symbol
    for index, pin_stack in enumerate(pin_stacks):
        # Calculate pos for pin stack
        posy = posy_func(index)
        posx = posx_func(index)
        # Add each pin of the stack
        for pos_in_stack, pin in enumerate(pin_stack):
            # Skip placing pins for spaces
            if pin.type == "space":
                continue
            # Move in no_connect pins to meet KLC S4.6
            if pin.type == "no_connect":
                if rotation % 180 == 0:
                    posx += -pin_length if posx > 0 else pin_length
                else:
                    posy += -pin_length if posy > 0 else pin_length
            etype = pin.type
            # Set type passive according to KLC S4.3 7,8
            if pos_in_stack != 0 and pin.type in ["power_in", "power_out", "output"]:
                etype = "passive"
            # Add the pin to the symbol
            new_symbol.pins.append(
                Pin(
                    number=str(pin.pin_number),
                    name=pin.name,
                    etype=etype,
                    posx=mil_to_mm(posx),
                    posy=mil_to_mm(posy),
                    is_hidden=(pos_in_stack != 0 or pin.type == "no_connect"),
                    rotation=rotation,
                    length=mil_to_mm(pin_length),
                    altfuncs=list(
                        map(lambda n: AltFunction(name=n, etype=etype), pin.alt_names)
                    ),
                    unit=unit_index,
                )
            )


# the actual main function of the parser when invoked as a script:
if __name__ == "__main__":
    # parse cmdline parameters
    parser = argparse.ArgumentParser(
        prog="from_csv_generator.py", description="Generates KiCad Symbols from CSVs."
    )
    parser.add_argument("input_csv_file", help="The CSV file to generate a symbol for.")
    parser.add_argument(
        "-o",
        "--output",
        help="Where to output the generated symbol to. If not given the path of the"
        + " input CSV with the extension .kicad_sym is used.",
    )
    parser.add_argument(
        "--split-alt-pinnames",
        type=int,
        dest="split",
        help="If given split pin names on '/' into alt pin names."
        + " An integer can be given to ignore the first n '/'."
        + " The default is to do no splitting.",
    )
    parser.add_argument(
        "--min-aspect-ratio",
        type=float,
        dest="min_aspect_ratio",
        help="The minimum aspect ratio to enforce for the generated symbol as width / height.",
    )

    cliArgs = parser.parse_args()

    # parse csv and get units
    try:
        metadata, pin_data = parse_csv(cliArgs.input_csv_file, cliArgs.split)
    except ValueError:
        print("error: can not parse input CSV. Is it properly formatted?")
        os._exit(1)

    symbol_units_dict = group_pins_by_unit(pin_data)
    unit_names_list = sorted(symbol_units_dict.keys())
    unit_names_dict = {(i + 1): name for i, name in enumerate(unit_names_list)}

    # generate kicad symbol

    libname = Path(cliArgs.input_csv_file).stem
    filename = libname + ".kicad_sym"

    if cliArgs.output:
        filename = cliArgs.output
        libname = Path(cliArgs.output).stem

    new_symbol = KicadSymbol.new(
        metadata.name,
        libname,
        reference=metadata.reference,
        footprint=metadata.footprint or "",
        datasheet=metadata.datasheet or "",
        keywords=metadata.keywords or "",
        description=metadata.description or "",
        fp_filters=metadata.footprint_filter or "",
        unit_names=unit_names_dict,
    )

    new_symbol.add_default_properties()
    new_symbol.unit_count = len(symbol_units_dict.keys())

    max_bounding_box_width = 0
    max_bounding_box_height = 0

    # for each unit add pins and bounding box rectangle
    for unit_index, unit_name in unit_names_dict.items():
        pins: List[PinData] = symbol_units_dict[unit_name]
        # group pins into stacks
        pin_stacks: Dict[PinData.Side, List[PinStack]] = {
            side: create_pin_stacks(pins)
            for side, pins in group_pins_by_side(pins).items()
        }

        # get base bounding box
        base_bounding_box = calculate_base_bounding_box_size(pin_stacks)

        # Calculate pin length according to KLC S4.1
        max_pin_number_length = max(list(map(lambda p: len(str(p.pin_number)), pins)))
        pin_length = min(max(100, max_pin_number_length * 50), 300)

        # extend bounding box to prevent pin label intersections
        bounding_box = extend_bounding_box(
            pin_stacks, base_bounding_box, pin_length, cliArgs.min_aspect_ratio
        )
        bounding_box_width, bounding_box_height = bounding_box

        if bounding_box_width > max_bounding_box_width:
            max_bounding_box_width = bounding_box_width
        if bounding_box_height > max_bounding_box_height:
            max_bounding_box_height = bounding_box_height

        # generate pins for each side
        generate_pins(
            pin_stacks[PinData.Side.LEFT],
            lambda i: -bounding_box_width / 2 - pin_length,
            lambda i: pos_for_pin(len(pin_stacks[PinData.Side.LEFT]), i, False),
            0,
            pin_length,
            unit_index,
        )

        generate_pins(
            pin_stacks[PinData.Side.RIGHT],
            lambda i: bounding_box_width / 2 + pin_length,
            lambda i: pos_for_pin(len(pin_stacks[PinData.Side.RIGHT]), i, False),
            180,
            pin_length,
            unit_index,
        )

        generate_pins(
            pin_stacks[PinData.Side.TOP],
            lambda i: pos_for_pin(len(pin_stacks[PinData.Side.TOP]), i, True),
            lambda i: bounding_box_height / 2 + pin_length,
            270,
            pin_length,
            unit_index,
        )

        generate_pins(
            pin_stacks[PinData.Side.BOTTOM],
            lambda i: pos_for_pin(len(pin_stacks[PinData.Side.BOTTOM]), i, True),
            lambda i: -bounding_box_height / 2 - pin_length,
            90,
            pin_length,
            unit_index,
        )

        # add bounding box rectangle
        new_symbol.rectangles.append(
            Rectangle(
                mil_to_mm(bounding_box_width / 2),
                mil_to_mm(bounding_box_height / 2),
                mil_to_mm(-bounding_box_width / 2),
                mil_to_mm(-bounding_box_height / 2),
                stroke_width=mil_to_mm(10),
                unit=unit_index,
            )
        )

    # add symbol metadata
    label_reference = new_symbol.get_property("Reference")
    label_reference.posx = mil_to_mm(-max_bounding_box_width / 2)
    label_reference.posy = mil_to_mm(max_bounding_box_height / 2 + 100)

    label_value = new_symbol.get_property("Value")
    label_value.posx = mil_to_mm(max_bounding_box_width / 2)
    label_value.posy = mil_to_mm(max_bounding_box_height / 2 + 100)

    label_datasheet = new_symbol.get_property("Datasheet")
    label_datasheet.posx = mil_to_mm(0)
    label_datasheet.posy = mil_to_mm(-max_bounding_box_height / 2 - 600)

    label_description = new_symbol.get_property("Description")
    label_description.posx = mil_to_mm(0)
    label_description.posy = mil_to_mm(-max_bounding_box_height / 2 - 800)
    label_description.effects.v_justify = "top"

    # save library with symbol
    lib = KicadLibrary(filename)
    lib.symbols.append(new_symbol)

    lib.write()

    print(f"Written generated symbol to {filename}")
