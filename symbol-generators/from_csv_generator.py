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

from kicad_sym import KicadLibrary, KicadSymbol, Pin, AltFunction, Rectangle, mil_to_mm
import argparse
import csv
import math
from pathlib import Path
from collections import OrderedDict

CHAR_WIDTH_GUESSTIMATE = 50
PIN_NAME_LIMIT = 12

# parse cmdline parameters
parser = argparse.ArgumentParser(
                    prog='from_csv_generator.py',
                    description='Generates KiCad Symbols from CSVs.')
parser.add_argument('filename')
parser.add_argument('-o', '--output')
parser.add_argument('--split-alt-pinnames', type=int, dest='split')
parser.add_argument('--min-aspect-ratio', type=float, dest='min_aspect_ratio')

args = parser.parse_args()

# parse input CSV

metadata = {}
in_metadata_section = True

pin_headers = None
pin_data = []

with open(args.filename, newline='') as csvfile:
    reader = csv.reader(filter(lambda row: not row.startswith('# '), csvfile))  # filter out lines with comments
    for row in reader:
        if in_metadata_section:  # parse metadata
            if len(row) == 0 or len(row[0].strip()) == 0:  # skip from metadata to pin data on first empty line
                in_metadata_section = False

                # check required keys
                required_key_missing = False
                if 'reference' not in metadata.keys():
                    print('error: key "reference" is missing in the metadata')
                    required_key_missing = True
                if 'name' not in metadata.keys():
                    print('error: key "name" is missing in the metadata')
                    required_key_missing = True
                if 'footprint' not in metadata.keys():
                    print('warning: key "footprint" is missing in the metadata')
                if 'footprint_filter' not in metadata.keys():
                    print('warning: key "footprint_filter" is missing in the metadata')
                if 'datasheet' not in metadata.keys():
                    print('warning: key "datasheet" is missing in the metadata')
                if 'description' not in metadata.keys():
                    print('warning: key "description" is missing in the metadata')
                if 'keywords' not in metadata.keys():
                    print('warning: key "keywords" is missing in the metadata')
                if required_key_missing:
                    os._exit(1)

                continue
            else:  # add row to metadata
                metadata_key = row[0].lower().replace(' ', '_')
                metadata_value = row[1]
                if metadata_key not in metadata:
                    if len(metadata_value) > 0:
                        metadata[metadata_key] = metadata_value
                else:
                    print(f'error: metadata key "{metadata_key}" defined multiple times', file=sys.stderr)
                    os._exit(1)
        else:  # parse pin data
            if len(row) == 0 or all(map(lambda cell: cell == '', row)):  # skip empty rows
                continue
            elif pin_headers is None:  # treat first pin data row as header names/order
                pin_headers = list(map(lambda h: h.lower(), filter(lambda h: len(h) > 0, row)))

                required_key_missing = False
                if 'pin' not in pin_headers:
                    print('error: key "pin" is missing in the header row')
                    required_key_missing = True
                if 'name' not in pin_headers:
                    print('error: key "name" is missing in the header row')
                    required_key_missing = True
                if 'type' not in pin_headers:
                    print('error: key "type" is missing in the header row')
                    required_key_missing = True
                if 'side' not in pin_headers:
                    print('warning: key "side" is missing in the header row')
                if required_key_missing:
                    os._exit(1)
            else:
                parsed_pin_data = {}

                for column, header in enumerate(pin_headers):
                    if column >= len(row):
                        break
                    parsed_pin_data[header] = row[column]

                parsed_pin_data['type'] = parsed_pin_data['type'].lower().replace(' ', '_')
                parsed_pin_data['side'] = parsed_pin_data['side'].lower().replace(' ', '_')

                if args.split is not None:
                    pin_names = list(map(str.strip, parsed_pin_data['name'].split('/')))
                    split_index = max(args.split, 1)
                    parsed_pin_data['name'] = '/'.join(pin_names[:split_index])
                    parsed_pin_data['alt_names'] = pin_names[split_index:]
                else:
                    parsed_pin_data['alt_names'] = []

                if len(parsed_pin_data['name']) > PIN_NAME_LIMIT:
                    print(f'warning: pin name "{parsed_pin_data['name']}" is longer than {PIN_NAME_LIMIT} characters')

                if parsed_pin_data['pin'] == '':
                    pin_data.append(parsed_pin_data)
                else:
                    for pin_num_str in parsed_pin_data['pin'].split(','):
                        pin_range_arr = pin_num_str.split('-', maxsplit=1)
                        pin_range_start = int(pin_range_arr[0].strip())
                        pin_range_end = int(pin_range_arr[1].strip()) if len(pin_range_arr) > 1 else pin_range_start
                        pin_range = range(pin_range_start, pin_range_end + 1)
                        for pin_num in pin_range:
                            new_pin = parsed_pin_data.copy()
                            new_pin['pin'] = str(pin_num)
                            pin_data.append(new_pin)


# group pins according to side
pins_left = [pin for pin in pin_data if pin['side'] == 'left']
pins_right = [pin for pin in pin_data if pin['side'] == 'right' or pin['side'] == '']
pins_top = [pin for pin in pin_data if pin['side'] == 'top']
pins_bottom = [pin for pin in pin_data if pin['side'] == 'bottom']


def create_pin_stacks(pins):
    """Groups together the given pins by their name to create stacks of same pins.

        Parameters:
            pins (list): A list of pin data.

        Returns:
            list: A list of lists each containing a group of pins with the same name.
    """
    # mapping of pin names to pin pin_stacks
    pin_stacks = OrderedDict()
    # go through all pins and sort them into pin_stacks
    for index, pin in enumerate(pins):
        pin_name = pin.get('name')
        # do not group spaces and no_connects
        if pin['type'] == 'space' or pin['type'] == 'no_connect':
            pin_stacks[f'do_not_group_{index}'] = [pin]
        # add pins to existing pin_stacks
        elif pin_name in pin_stacks:
            pin_stacks[pin_name].append(pin)
        # create new pin_stacks for new pin names
        else:
            pin_stacks[pin_name] = [pin]
    # return list of pin stacks where the pins in each stack are sorted by pin number
    return list(map(lambda g: sorted(g, key=lambda p: p['pin']), pin_stacks.values()))


# group pins for each side with the same name together to create pin stacks
pin_stacks_left = create_pin_stacks(pins_left)
pin_stacks_right = create_pin_stacks(pins_right)
pin_stacks_top = create_pin_stacks(pins_top)
pin_stacks_bottom = create_pin_stacks(pins_bottom)

pin_count_horizontal = max(len(pin_stacks_top), len(pin_stacks_bottom))
pin_count_vertical = max(len(pin_stacks_left), len(pin_stacks_right))


def pos_for_pin(pin_count, index, direction=1):
    """Calculates the position for the pin at the given index.

        Parameters:
            pin_count (int): The total number of pins on the axis to calculate the position for.
            index (int): The index of the pin to calculate the position for.
            direction (int): 1 or -1 whether the highest pin is on the positive or negative side of the axis.

        Returns:
            int: The position of the pin at the given index.
    """
    return (-direction * (pin_count // 2) * 100) + (direction * index * 100)


def pin_label_width(pin):
    """Calculates the estimated width of the label of the given pin.

        Parameters:
            pin (object): The pin data to calculate the label width for.

        Returns:
            int: The estimated width of the pin's label.
    """
    return (len(pin['name']) + 1) * CHAR_WIDTH_GUESSTIMATE


# Calculate base bounding box size
total_horizontal_pin_width = (pin_count_horizontal + 1) * 100
max_pin_name_length_left = max((pin_label_width(pin) for pin, *others in pin_stacks_left),
                               default=0)
max_pin_name_length_right = max((pin_label_width(pin) for pin, *others in pin_stacks_right),
                                default=0)

bounding_box_width = (max(total_horizontal_pin_width,
                          max_pin_name_length_left,
                          max_pin_name_length_right,
                          200) // 200 + 1) * 200


total_vertical_pin_width = (pin_count_vertical + 1) * 100
max_pin_name_length_top = max((pin_label_width(pin) for pin, *others in pin_stacks_top),
                              default=0)
max_pin_name_length_bottom = max((pin_label_width(pin) for pin, *others in pin_stacks_bottom),
                                 default=0)

bounding_box_height = (max(total_vertical_pin_width,
                           max_pin_name_length_top,
                           max_pin_name_length_bottom,
                           200) // 200 + 1) * 200

# Calculate pin length according to KLC S4.1
max_pin_number_length = max(list(map(lambda p: len(p['pin']), pin_data)))
pin_length = min(max(100, max_pin_number_length * 50), 300)


def check_label_intersection(pin_stacks, pin_stacks_opposite, b_height, b_width):
    """Checks if the labels of the given pin_stacks intersect with the labels of the opposite side.

        Parameters:
            pin_stacks (list): A list of pin stacks to check the intersection of labels for.
            pin_stacks_opposite (list): The list of pin stacks on the opposite side.
            b_height (int): The current height of the bounding box.
            b_width (int): The current width of the bounding box.

        Returns:
            bool: Whether the labels of pin_stacks intersect with the labels of the opposite side or not.
    """
    # Check intersection for all given pin stacks
    for i, pin_stack in enumerate(pin_stacks):
        pin = pin_stack[0]  # Use first pin in stack as pin stacks are grouped by label/name
        length = pin_label_width(pin)
        x_pos = pos_for_pin(len(pin_stacks), i, 1)
        y_pos = -b_height / 2 - pin_length

        # Check intersection with each pin stack on the opposite side
        for j, pin_stack_opposite in enumerate(pin_stacks_opposite):
            pin_opposite = pin_stack_opposite[0]
            length_opposite = pin_label_width(pin_opposite)
            x_pos_opposite = pos_for_pin(len(pin_stack_opposite), j, 1)
            y_pos_opposite = b_height / 2 + pin_length

            # Check intersection of the two labels
            if (x_pos_opposite < x_pos + 100 and
               x_pos_opposite + 100 > x_pos and
               y_pos + length > y_pos_opposite - length_opposite - 50):
                return True  # Return if one pair of labels intersect

    return False


# Extend bounding box size until no pin labels intersect
intersect_top = True
intersect_bottom = True
intersect_left = True
intersect_right = True

while intersect_top or intersect_bottom or intersect_left or intersect_right:

    intersect_top = check_label_intersection(pin_stacks_top,
                                             pin_stacks_bottom,
                                             bounding_box_height,
                                             bounding_box_width)

    intersect_bottom = check_label_intersection(pin_stacks_bottom,
                                                pin_stacks_top,
                                                bounding_box_height,
                                                bounding_box_width)

    if intersect_top or intersect_bottom:
        bounding_box_height += 200

    intersect_left = check_label_intersection(pin_stacks_left,
                                              pin_stacks_right,
                                              bounding_box_width,
                                              bounding_box_height)

    intersect_right = check_label_intersection(pin_stacks_right,
                                               pin_stacks_left,
                                               bounding_box_width,
                                               bounding_box_height)

    if intersect_left or intersect_right:
        bounding_box_width += 200

if args.min_aspect_ratio is not None and bounding_box_width / bounding_box_height < args.min_aspect_ratio:
    bounding_box_width = int(math.ceil(bounding_box_height * args.min_aspect_ratio / 200.0) * 200)

# generate kicad symbol

libname = Path(args.filename).stem
filename = libname + '.kicad_sym'

if args.output:
    filename = args.output
    libname = Path(args.output).stem

new_symbol = KicadSymbol.new(metadata.get('name', ''),
                             libname,
                             reference=metadata.get('reference', ''),
                             footprint=metadata.get('footprint', ''),
                             datasheet=metadata.get('datasheet', ''),
                             keywords=metadata.get('keywords', ''),
                             description=metadata.get('description', ''),
                             fp_filters=metadata.get('footprint_filter', ''))

lib = KicadLibrary(filename)
lib.symbols.append(new_symbol)

# add symbol metadata
new_symbol.add_default_properties()

label_reference = new_symbol.get_property("Reference")
label_reference.posx = mil_to_mm(-bounding_box_width / 2)
label_reference.posy = mil_to_mm(bounding_box_height / 2 + 100)

label_value = new_symbol.get_property("Value")
label_value.posx = mil_to_mm(bounding_box_width / 2)
label_value.posy = mil_to_mm(bounding_box_height / 2 + 100)

label_datasheet = new_symbol.get_property("Datasheet")
label_datasheet.posx = mil_to_mm(0)
label_datasheet.posy = mil_to_mm(-bounding_box_height / 2 - 600)

label_description = new_symbol.get_property("Description")
label_description.posx = mil_to_mm(0)
label_description.posy = mil_to_mm(-bounding_box_height / 2 - 800)
label_description.effects.v_justify = 'top'

# add symbol pins


def generate_pins(pin_stacks, posx_func, posy_func, rotation):
    """Adds the given pin stacks to the new symbol using the given functions and rotation to determine pin positions.

        Parameters:
            pin_stacks (list): The list of pin stacks to place where each is a list of pins.
            posx_func (func): Function returning the x position of a pin (stack) for a given index.
            posy_func (func): Function returning the y position of a pin (stack) for a given index.
            rotation (int): The rotation/orientation of the pins.
   """
    # Add all given pin stacks to the symbol
    for index, pin_stack in enumerate(pin_stacks):
        # Calculate pos for pin stack
        posy = posy_func(index)
        posx = posx_func(index)
        # Add each pin of the stack
        for pos_in_stack, pin in enumerate(pin_stack):
            # Skip placing pins for spaces
            if pin['type'] == 'space':
                continue
            # Move in no_connect pins to meet KLC S4.6
            if pin['type'] == 'no_connect':
                if rotation % 180 == 0:
                    posx += -pin_length if posx > 0 else pin_length
                else:
                    posy += -pin_length if posy > 0 else pin_length
            etype = pin['type']
            # Set type passive according to KLC S4.3 7,8
            if pos_in_stack != 0 and pin['type'] in ['power_in', 'power_out', 'output']:
                etype = 'passive'
            # Add the pin to the symbol
            new_symbol.pins.append(
                Pin(number=pin['pin'],
                    name=pin['name'],
                    etype=etype,
                    posx=mil_to_mm(posx),
                    posy=mil_to_mm(posy),
                    is_hidden=(pos_in_stack != 0 or pin['type'] == 'no_connect'),
                    rotation=rotation,
                    length=mil_to_mm(pin_length),
                    altfuncs=list(map(lambda n: AltFunction(name=n, etype=etype), pin['alt_names'])))
            )


# generate pins for each side
generate_pins(pin_stacks_left,
              lambda i: -bounding_box_width / 2 - pin_length,
              lambda i: pos_for_pin(len(pin_stacks_left), i, -1),
              0)

generate_pins(pin_stacks_right,
              lambda i: bounding_box_width / 2 + pin_length,
              lambda i: pos_for_pin(len(pin_stacks_right), i, -1),
              180)

generate_pins(pin_stacks_top,
              lambda i: pos_for_pin(len(pin_stacks_top), i, 1),
              lambda i: bounding_box_height / 2 + pin_length,
              270)

generate_pins(pin_stacks_bottom,
              lambda i: pos_for_pin(len(pin_stacks_bottom), i, 1),
              lambda i: -bounding_box_height / 2 - pin_length,
              90)

# add bounding box
new_symbol.rectangles.append(Rectangle(mil_to_mm(bounding_box_width / 2),
                                       mil_to_mm(bounding_box_height / 2),
                                       mil_to_mm(-bounding_box_width / 2),
                                       mil_to_mm(-bounding_box_height / 2),
                                       stroke_width=mil_to_mm(10)))

# save library with symbol
lib.write()
