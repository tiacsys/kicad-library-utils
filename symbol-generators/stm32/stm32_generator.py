#!/usr/bin/env python3

import pathlib
import sqlite3
import os
import re
import time
import math
import sys
from collections import defaultdict
import warnings
import fnmatch
from itertools import groupby
from dataclasses import dataclass, field

import httpx
import click
from bs4 import BeautifulSoup
import tqdm

common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, "common")
)
if common not in sys.path:
    sys.path.insert(0, common)

common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, "common")
)
if common not in sys.path:
    sys.path.insert(0, common)

import kicad_sym
from DrawingElements import Drawing, DrawingPin, DrawingRectangle, ElementFill
from Point import Point


# Match everything before the first separator, which may be one of [space], /, -.
# However, do match dashes (-) when they are the last character in the name (VREF-)
_PINNAME_MATCH = re.compile("[^ /-]*(-$)?")


@dataclass
class DataPin:
    num: str  # may also be an BGA pin coordinate
    name: str
    pintype: str
    altfuncs: list = field(default_factory=list)
    graphical_type: str = 'other'
    electrical_type: str = 'input'

    def __post_init__(self):
        # Maps regex for {XML pintype}/{XML pin name} to {graphical}/{electrical} type.
        # Graphical type is used by this script further down to determine placement,
        # and electrical type is saved in the symbol for KiCad's electrical rule check.
        type_lookup = {r'(Power|MonoIO)/VREF':   'special_power/input',
                       r'Power/VCAP':            'vcap/power_output',
                       r'Power/(VDD|VBAT|VLCD)': 'vdd/power_input',
                       r'Power/VSS':             'vss/power_input',
                       r'Power/VFB':             'other/input',
                       r'Power/VLCD':            'vdd/power_output',
                       r'Power/REGOFF':          'other/input',
                       r'Power/RFU':             'nc/nc',
                       r'Power/PDR_ON':          'other/input',
                       r'Power/PWR_(ON|LP)':     'other/output',
                       r'Power/IRROFF':          'other/input',
                       r'Power/NPOR':            'other/input',
                       r'I/O/PWR_CPU_ON':        'other/output',
                       r'Power/':                'special_power/power_input',
                       r'(I/O|MonoIO)/(.*-)?OSC_(IN|OUT)':      'clock/input',
                       r'I/O/(OPAMP|AOP).*':     'other/input',
                       r'I/O':                   'port/bidir',
                       r'Clock/P([A-Z)([0-9]+)': 'port/bidir',
                       r'Clock/':                'clock/input',
                       r'Reset/':                'reset/input',
                       r'Boot/':                 'boot/input',
                       r'NC/':                   'nc/nc',
                       r'MonoIO/':               'monoio/bidir',
                       }

        name_lookup = {
            "PC14OSC32_IN": "PC14",
            "PC15OSC32_OUT": "PC15",
            "PF11BOOT0": "PF11",
        }

        self.name = name_lookup.get(self.name, _PINNAME_MATCH.match(self.name).group())

        for k, v in type_lookup.items():
            if re.match(k, f'{self.pintype}/{self.name}'):
                self.graphical_type, self.electrical_type = v.split('/')
                break
        else:
            self.graphical_type = 'other'

    def draw(self, pin_length=200, direction='left', x=0, y=0, visible=True):
        visibility = DrawingPin.PinVisibility.VISIBLE if visible else DrawingPin.PinVisibility.INVISIBLE # NOQA
        orientation = getattr(DrawingPin.PinOrientation, direction.upper())
        el_type = getattr(DrawingPin.PinElectricalType, f'EL_TYPE_{self.electrical_type.upper()}')

        # invisible stacked power pins should have passive electrical type or the linter gets angry
        if self.electrical_type == 'power_input' and not visible:
            el_type = DrawingPin.PinElectricalType.EL_TYPE_PASSIVE

        return DrawingPin(Point(x, y), self.num, orientation=orientation, visibility=visibility,
                          pin_length=pin_length, name=self.name, altfuncs=self.altfuncs,
                          el_type=el_type)


class Device:
    _name_search = re.compile(r"^(.+)\((.+)\)(.+)$")
    _pincount_search = re.compile(r"^[a-zA-Z]+([0-9]+)$")
    _pkgname_sub = re.compile(r"([a-zA-Z]+)([0-9]+)(-.*|)")

    # useful command for identifying datasheets in pdftotext output:
    # sha256sum (ag '^[^a-zA-Z]*[0-9][^a-zA-Z]*This (pin|ball) should' -l|sed s/.txt/.pdf/|sort)
    _NC_OVERRIDES = {
        # These parts have some NC pins with very specific requirements that are sadly not marked
        # in the source XML. The affected parts are all in TFBGA240 packages. On their sister
        # models, these pins are used for the internal switchmode regulator.
        # See https://gitlab.com/kicad/libraries/kicad-symbols/-/issues/3135
        r'STM32H74[23]X.*H.|STM32H750X.*H.|STM32H753X.*H.': {
            'F1': ('Power', 'VDD_OR_VSS'),
            'F2': ('Power', 'VSS'),
            'G2': ('Power', 'VSS')
        },
    }
    _POWER_PAD_FIX_PACKAGES = {"UFQFPN32", "UFQFPN48", "VFQFPN36", "VFQFPN68"}
    _FOOTPRINT_MAPPING = {
            "SO8N":         ("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",                         "SO*3.9x4.9mm*P1.27mm*"), # NOQA
            "LFBGA100":     ("Package_BGA:LFBGA-100_10x10mm_Layout10x10_P0.8mm",            "*LFBGA*10x10mm*Layout10x10*P0.8mm*"), # NOQA
            "LFBGA144":     ("Package_BGA:LFBGA-144_10x10mm_Layout12x12_P0.8mm",            "*LFBGA*10x10mm*Layout12x12*P0.8mm*"), # NOQA
            "LFBGA289":     ("Package_BGA:LFBGA-289_14x14mm_Layout17x17_P0.8mm",            "*LFBGA*14x14mm*Layout17x17*P0.8mm*"), # NOQA
            "LFBGA354":     ("Package_BGA:ST_LFBGA-354_16x16mm_Layout19x19_P0.8mm",         "*LFBGA*16x16mm*Layout19x19*P0.8mm*"), # NOQA
            "LFBGA448":     ("Package_BGA:ST_LFBGA-448_18x18mm_Layout22x22_P0.8mm",         "*LFBGA*18x18mm*Layout22x22*P0.8mm*"), # NOQA
            "LQFP32":       ("Package_QFP:LQFP-32_7x7mm_P0.8mm",                            "LQFP*7x7mm*P0.8mm*"), # NOQA
            "LQFP48":       ("Package_QFP:LQFP-48_7x7mm_P0.5mm",                            "LQFP*7x7mm*P0.5mm*"), # NOQA
            "LQFP64":       ("Package_QFP:LQFP-64_10x10mm_P0.5mm",                          "LQFP*10x10mm*P0.5mm*"), # NOQA
            "LQFP80-12X12": ("Package_QFP:LQFP-80_12x12mm_P0.5mm",                          "LQFP*12x12mm*P0.5mm*"), # NOQA
            "LQFP80-14X14": ("Package_QFP:LQFP-80_14x14mm_P0.65mm",                         "LQFP*14x14mm*P0.65mm*"), # NOQA
            "LQFP100":      ("Package_QFP:LQFP-100_14x14mm_P0.5mm",                         "LQFP*14x14mm*P0.5mm*"), # NOQA
            "LQFP128":      ("Package_QFP:LQFP-128_14x14mm_P0.4mm",                         "LQFP*14x14mm*P0.4mm*"), # NOQA
            "LQFP144":      ("Package_QFP:LQFP-144_20x20mm_P0.5mm",                         "LQFP*20x20mm*P0.5mm*"), # NOQA
            "LQFP176":      ("Package_QFP:LQFP-176_24x24mm_P0.5mm",                         "LQFP*24x24mm*P0.5mm*"), # NOQA
            "LQFP208":      ("Package_QFP:LQFP-208_28x28mm_P0.5mm",                         "LQFP*28x28mm*P0.5mm*"), # NOQA
            "TFBGA64":      ("Package_BGA:TFBGA-64_5x5mm_Layout8x8_P0.5mm",                 "TFBGA*5x5mm*Layout8x8*P0.5mm*"), # NOQA
            "TFBGA100":     ("Package_BGA:TFBGA-100_8x8mm_Layout10x10_P0.8mm",              "TFBGA*8x8mm*Layout10x10*P0.8mm*"), # NOQA
            "TFBGA169":     ("Package_BGA:ST_TFBGA-169_7x7mm_Layout13x13_P0.5mm",           "TFBGA*7x7mm*Layout13x13*P0.5mm*"), # NOQA
            "TFBGA216":     ("Package_BGA:TFBGA-216_13x13mm_Layout15x15_P0.8mm",            "TFBGA*13x13mm*Layout15x15*P0.8mm*"), # NOQA
            "TFBGA225":     ("Package_BGA:ST_TFBGA-225_13x13mm_Layout15x15_P0.8mm",         "*TFBGA*13x13mm*Layout15x15*P0.8mm*"), # NOQA
            "TFBGA240":     ("Package_BGA:TFBGA-265_14x14mm_Layout17x17_P0.8mm",            "TFBGA*14x14mm*Layout17x17*P0.8mm*"), # NOQA
            "TFBGA257":     ("Package_BGA:ST_TFBGA-257_10x10mm_Layout19x19_P0.5mmP0.65mm",  "*TFBGA*10x10mm*Layout19x19*P0.5mmP0.65mm*"), # NOQA
            "TFBGA289":     ("Package_BGA:TFBGA-289_9x9mm_Layout17x17_P0.5mm",              "*TFBGA*9x9mm*Layout17x17*P0.5mmP0.65mm*"), # NOQA
            "TFBGA320":     ("Package_BGA:ST_TFBGA-320_11x11mm_Layout21x21_P0.5mm",         "*TFBGA*11x11mm_Layout21x21*P0.5mm"), # NOQA
            "TFBGA361":     ("Package_BGA:ST_TFBGA-361_12x12mm_Layout23x23_P0.5mmP0.65mm",  "*TFBGA*12x12mm*Layout23x23*P0.5mmP0.65mm*"), # NOQA
            "TSSOP14":      ("Package_SO:TSSOP-14_4.4x5mm_P0.65mm",                         "TSSOP*4.4x5mm*P0.65mm*"), # NOQA
            "TSSOP20":      ("Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",                       "TSSOP*4.4x6.5mm*P0.65mm*"), # NOQA
            "UFBGA64":      ("Package_BGA:UFBGA-64_5x5mm_Layout8x8_P0.5mm",                 "*UFBGA*5x5mm*Layout8x8*P0.5mm*"), # NOQA
            "UFBGA73":      ("Package_BGA:ST_UFBGA-73_5x5mm_Layout9x9_P0.5mm",              "*UFBGA*5x5mm*Layout9x9*P0.5mm*"), # NOQA
            "UFBGA100":     ("Package_BGA:UFBGA-100_7x7mm_Layout12x12_P0.5mm",              "*UFBGA*7x7mm*Layout12x12*P0.5mm*"), # NOQA
            "UFBGA121":     ("Package_BGA:ST_UFBGA-121_6x6mm_Layout11x11_P0.5mm",           "*UFBGA*6x6mm*Layout11x11*P0.5mm*"), # NOQA
            "UFBGA129":     ("Package_BGA:ST_UFBGA-129_7x7mm_Layout13x13_P0.5mm",           "*UFBGA*7x7mm*Layout13x13*P0.5mm*"), # NOQA
            "UFBGA132":     ("Package_BGA:UFBGA-132_7x7mm_Layout12x12_P0.5mm",              "*UFBGA*7x7mm*Layout12x12*P0.5mm*"), # NOQA
            "UFBGA144-7X7": ("Package_BGA:UFBGA-144_7x7mm_Layout12x12_P0.5mm",              "*UFBGA*7x7mm*Layout12x12*P0.5mm*"), # NOQA
            "UFBGA144-10X10":("Package_BGA:UFBGA-144_10x10mm_Layout12x12_P0.8mm",           "*UFBGA*10x10mm*Layout12x12*P0.8mm*"), # NOQA
            "UFBGA169":     ("Package_BGA:UFBGA-169_7x7mm_Layout13x13_P0.5mm",              "*UFBGA*7x7mm*Layout13x13*P0.5mm*"), # NOQA
            "UFBGA176":     ("Package_BGA:UFBGA-201_10x10mm_Layout15x15_P0.65mm",           "*UFBGA*10x10mm*Layout15x15*P0.65mm*"), # NOQA
            "UFQFPN20":     ("Package_DFN_QFN:ST_UFQFPN-20_3x3mm_P0.5mm",                   "ST*UFQFPN*3x3mm*P0.5mm*"), # NOQA
            "UFQFPN28":     ("Package_DFN_QFN:QFN-28_4x4mm_P0.5mm",                         "QFN*4x4mm*P0.5mm*"), # NOQA
            "UFQFPN32":     ("Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm",       "QFN*1EP*5x5mm*P0.5mm*"), # NOQA
            "VFQFPN36":     ("Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm",         "QFN*1EP*6x6mm*P0.5mm*"), # NOQA
            "UFQFPN48":     ("Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",         "QFN*1EP*7x7mm*P0.5mm*"), # NOQA
            "VFQFPN68":     ("Package_DFN_QFN:QFN-68-1EP_8x8mm_P0.4mm_EP6.4x6.4mm",         "QFN*1EP*8x8mm*P0.4mm*"), # NOQA
    }
    _WLCSP_MAP = {
            'ST_WLCSP-100_Die495': ('Package_CSP:ST_WLCSP-100_4.40x4.38mm_Layout10x10_P0.4mm_Offcenter', '*'), # NOQA
            'ST_WLCSP-100_Die471': ('Package_CSP:ST_WLCSP-100_4.437x4.456mm_Layout10x10_P0.4mm', '*'), # NOQA
            'ST_WLCSP-115_Die483': ('Package_CSP:ST_WLCSP-115_3.73x4.15mm_P0.35mm_Stagger', '*'), # NOQA
            'ST_WLCSP-115_Die461': ('Package_CSP:ST_WLCSP-115_4.63x4.15mm_P0.4mm_Stagger', '*'), # NOQA
            'ST_WLCSP-132_Die480': ('Package_CSP:ST_WLCSP-132_4.57x4.37mm_Layout12x11_P0.35mm', '*'), # NOQA
            'ST_WLCSP-156_Die450': ('Package_CSP:ST_WLCSP-156_4.96x4.64mm_Layout13x12_P0.35mm', '*'), # NOQA
            'ST_WLCSP-18_Die466':  ('Package_CSP:ST_WLCSP-18_1.86x2.14mm_P0.4mm_Stagger', '*'), # NOQA
            'ST_WLCSP-25_Die460':  ('Package_CSP:ST_WLCSP-25_2.30x2.48mm_Layout5x5_P0.4mm', '*'), # NOQA
            'ST_WLCSP-36_Die464':  ('Package_CSP:ST_WLCSP-36_2.58x3.07mm_Layout6x6_P0.4mm', '*'), # NOQA
            'ST_WLCSP-49_Die468':  ('Package_CSP:ST_WLCSP-49_3.15x3.13mm_Layout7x7_P0.4mm', '*'), # NOQA
            'ST_WLCSP-64_Die479':  ('Package_CSP:ST_WLCSP-64_3.56x3.52mm_Layout8x8_P0.4mm', '*'), # NOQA
            'ST_WLCSP-81_Die469':  ('Package_CSP:ST_WLCSP-81_4.02x4.27mm_Layout9x9_P0.4mm', '*'), # NOQA
            'ST_WLCSP-81_Die472':  ('Package_CSP:ST_WLCSP-81_4.36x4.07mm_Layout9x9_P0.4mm', '*'), # NOQA
            'ST_WLCSP-20_Die456':  ('Package_CSP:ST_WLCSP-20_1.94x2.40mm_Layout4x5_P0.4mm', '*'), # NOQA
            'ST_WLCSP-49_Die494':  ('Package_CSP:ST_WLCSP-49_3.30x3.38mm_Layout7x7_P0.4mm_Offcenter', '*'), # NOQA
            'ST_WLCSP-52_Die467':  ('Package_CSP:ST_WLCSP-52_3.09x3.15mm_P0.4mm_Stagger', '*'), # NOQA
            'ST_WLCSP-90_Die482':  ('Package_CSP:ST_WLCSP-90_4.20x3.95mm_P0.4mm_Stagger', '*'), # NOQA
            'ST_WLCSP-12_Die443':  ('Package_CSP:ST_WLCSP-12_1.70x1.42mm_P0.35mm_Stagger', '*'), # NOQA
            'ST_WLCSP-25_Die474':  ('Package_CSP:ST_WLCSP-25_2.33x2.24mm_Layout5x5_P0.4mm', '*'), # NOQA
            'ST_WLCSP-80_Die484':  ('Package_CSP:ST_WLCSP-80_3.50x3.27mm_P0.35mm_Stagger', '*'), # NOQA
            'ST_WLCSP-208_Die481': ('Package_CSP:ST_WLCSP-208_5.38x5.47mm_P0.35mm_Stagger', '*'), # NOQA
            'ST_WLCSP-150_Die481': ('Package_CSP:ST_WLCSP-150_5.38x5.47mm_P0.4m_Stagger', '*'), # NOQA
            'ST_WLCSP-56_Die455':  ('Package_CSP:ST_WLCSP-56_3.38x3.38mm_P0.4m_Stagger', '*'), # NOQA
            'ST_WLCSP-72_Die455':  ('Package_CSP:ST_WLCSP-72_3.38x3.38mm_P0.35m_Stagger', '*'), # NOQA
    }

    def __init__(self, xml):
        self.pins = []

        soup = BeautifulSoup(xml.read_text(), features='xml').find('Mcu')
        self.name = soup['RefName'].replace('(', '_').replace(')', '_')

        # Get the package code
        package = soup['Package']

        if package == "UFBGA144":
            # ST uses the name "UFBGA144" for two sizes of BGA, and there's no way to tell to pick
            # them apart besides the part number's package ID letter
            try:
                package += {
                        'H': '-7X7',
                        'I': '-7X7',
                        'J': '-10X10',
                        }[self.name[-2]]
            except KeyError:
                tqdm.tqdm.write('Unable to determine UFBGA144 variant (7x7mm or 10x10mm) '
                                f'for device {self.name}')

        elif package == "LQFP80":
            # Same as above
            try:
                package += {
                        'T': '-12X12',
                        'S': '-14X14',
                        }[self.name[-2]]
            except KeyError:
                tqdm.tqdm.write('Unable to determine LQFP80 variant '
                                f'(12x12mm/p0.5 or 14x14mm/p0.65) for device {self.name}')

        self.package = package

        if re.fullmatch('LGA[0-9]*', package):
            # These are RF SoMs that for some reason has an STM32 PN and ended
            # up in features.xml. Ignore them.
            self.footprint_filters = '*'
            self.footprint = ''

        elif (m := re.fullmatch(r'E?WLCSP([0-9]*)', package)):
            # Differentiate the WLCSP packages by die code
            die = soup.find('Die').text.title()

            if m.group(1) == '59' and die == 'Die497':
                # This chip has no datasheet, is not on ST's website and cannot be bought.
                self.footprint_filters = '*'
                self.footprint = ''

            elif m.group(1) == '99' and die == 'Die415':
                # This particular package is not documented in the chip's datasheet.
                self.footprint_filters = '*'
                self.footprint = ''

            else:
                pkg = f'ST_WLCSP-{m.group(1)}_{die}'

                if pkg in self._WLCSP_MAP:
                    self.footprint, self.footprint_filters = self._WLCSP_MAP[pkg]
                else:
                    self.footprint_filters = f'ST*WLCSP*{die}*'
                    self.footprint = f'Package_CSP:{pkg}'

        elif package in self._FOOTPRINT_MAPPING:
            self.footprint, self.footprint_filters = self._FOOTPRINT_MAPPING[self.package]

        else:
            tqdm.tqdm.write('No footprint/footprint filters found for '
                            f'device {self.name}, package {self.package}')
            self.footprint_filters = '*'
            self.footprint = ''

        for pattern, nc_override in self._NC_OVERRIDES.items():
            if re.fullmatch(pattern, self.name):
                break
        else:
            nc_override = {}

        # Read the information for each pin
        for child in soup.find_all('Pin'):
            pos, name, pintype = child['Position'], child['Name'], child['Type']

            # Apply overrides for semantically relevant pins that are not properly described in the
            # XML.
            # NOTE: The VDD*_Unused pins must not be mapped to NCs. They are necessary when
            # designing a board that should be upwards-compatible.
            if name in ('NC', 'DNU'):
                pintype, name = nc_override.get(pos, ('NC', name))

            altfuncs = []
            for signal in child.find_all('Signal'):
                altfunction = signal['Name']
                if altfunction != 'GPIO':
                    altfuncs.append(kicad_sym.AltFunction(altfunction, 'bidirectional', 'line'))

            self.pins.append(DataPin(pos, name, pintype, altfuncs))

        # If this part has a power pad, we have to add it manually
        if (soup['HasPowerPad'] == 'true' or self.package in Device._POWER_PAD_FIX_PACKAGES):
            # Read pin count from package name
            packPinCountR = Device._pincount_search.search(self.package)
            powerpinnumber = str(int(packPinCountR.group(1)) + 1)
            # Create power pad pin
            powerpadpin = DataPin(powerpinnumber, "VSS", "Power")
            self.pins.append(powerpadpin)

        # Merge any duplicated pins
        pinNumMap = {}
        removePins = []
        for pin in self.pins:
            if pin.num in pinNumMap:
                mergedPin = pinNumMap[pin.num]
                mergedPin.name += f"/{pin.name}"
                removePins.append(pin)
            else:
                pinNumMap[pin.num] = pin

        for pin in removePins:
            self.pins.remove(pin)

    def create_symbol(self, lib, keywords, desc, datasheet):
        # Make the symbol
        self.symbol = kicad_sym.KicadSymbol.new(self.name, lib.filename, "U", self.footprint,
                                                datasheet, keywords, desc, self.footprint_filters)

        lib.symbols.append(self.symbol)

        # Draw the symbol
        self.draw_symbol()

    def draw_symbol(self):
        pin_length = 100 if all(len(pin.num) < 3 for pin in self.pins) else 200

        pins = defaultdict(lambda: [])
        # Classify pins
        for pin in self.pins:
            pins[pin.graphical_type].append(pin)

        def pinkey(pin):
            """ Split pin name into alphabetic and numeric parts and parse numeric parts, for
            sorting. Example:

            'DDR1_DQ15B' -> ('DDR', 1, '_DQ', 15, 'B')
            """
            return tuple([int(num) if num else char
                          for num, char in re.findall('([0-9]+)|([^0-9]+)', pin.name)])

        pins = defaultdict(lambda: [], {
                k: sorted(v, key=pinkey) for k, v in pins.items()
            })

        def split_groups(pins, expr=r'.*'):
            """ Split pin list by either a regex or a list of regexes.

            If a single regex is given: Split list into one group for each distinct match value.
            E.g. for input P1A, P1B, P2A, P2B:

            'P.' -> [P1A, P1B], [P2A, P2B]

            If a list of regexis is given: Split the list into one group for each matching regex.
            e.g. for input USB_DP, USB_DM, ANA0, ANA1:

            ['USB.*', 'ANA.*'] -> [USB_DP, USB_DM], [ANA0, ANA1]
            """
            if isinstance(expr, str):
                pins = sorted(((re.match(expr, pin.name).group(0), pin) for pin in pins),
                              key=lambda e: e[0])
            else:
                expr = [re.compile(e) for e in [*expr, r'.*']]

                def match_pin(pin):
                    return next(i for i, e in enumerate(expr) if e.fullmatch(pinkey(pin)[0]))

                pins = sorted(((match_pin(pin), pin) for pin in pins),
                              key=lambda e: e[0])
            return [[e for key, e in group] for _key, group in groupby(pins, key=lambda e: e[0])]

        monoio_groups = [
                'DDR_BA.*',
                'DDR_A.*',
                'DDR_DQM.*',
                'DDR_DQS.*',
                'DDR_DQ.*',
                'DDR_.*',
                'JTCK|JTDI|JTDO|JTMS|NJTRST',
                'USB.*|OTG.*',
                'PDR.*|BYPASS_REG.*',
                'ANA.*']
        left = [pins['reset'],
                pins['boot'],
                pins['special_power'],
                pins['clock'],
                pins['other'],
                *split_groups(pins['monoio'], monoio_groups),
                pins['vcap']]

        unhandled = [pin.name for pin in pins['port'] if not re.match('P[A-Z][0-9]+', pin.name)]
        if unhandled:
            warnings.warn('Unhandled I/O pin name(s):'+' '.join(unhandled))
        # Split IO port pins in spaced groups by port number (i.e. PB0...15 [space] PC0...15 ...)
        right = split_groups(pins['port'], r'P.|.*')

        # [[1,2,3],[],[],[4,5,6],[7,8,9],[]] ->  [1, 2, 3, None, 4, 5, 6, None, 7, 8, 9]
        spaced = lambda groups: [e for group in groups for alt in [group, [None]] # NOQA
                                 for e in alt if group][:-1]
        spaced_len = lambda l: len(spaced(l)) # NOQA

        # Balance out pins on left and right sides
        while spaced_len(left) < spaced_len(right[:-1]):
            left.insert(-1, right.pop())  # insert before VCAP pin group

        # Calculate height of the symbol
        box_height = max(spaced_len(left), spaced_len(right))*100 + 200

        # Calculate the width of the symbol
        name_width = lambda pins: max(len(p.name)*47 for p in pins if p) if pins else 0 # NOQA

        spaced_left, spaced_right = spaced(left), spaced(right)
        names_left, names_right = name_width(spaced_left), name_width(spaced_right)

        stacked_vss = {key: list(group)
                       for key, group in groupby(pins['vss'], lambda pin: pin.name)}
        # this depends on dict being ordered
        pins['vss'] = [group[0] for group in stacked_vss.values()]

        spaced_top, spaced_bottom = pins['vdd'], pins['vss']
        top_width, bottom_width = len(spaced_top)*100, len(spaced_bottom)*100

        box_width = math.ceil(
                (names_left + max(top_width, bottom_width) + names_right + 100) / 100) * 100

        drawing = Drawing()
        drawing.append(DrawingRectangle(
                Point(0, 0), Point(box_width, box_height), unit_idx=0,
                fill=ElementFill.FILL_BACKGROUND))

        for i, pin in enumerate(spaced_left, start=1):
            if pin:
                drawing.append(pin.draw(pin_length, 'right', x=-pin_length, y=box_height - i*100))

        for i, pin in enumerate(spaced_right, start=1):
            if pin:
                drawing.append(pin.draw(pin_length, 'left',
                                        x=box_width+pin_length, y=box_height - i*100))

        last_top_x = 0
        for i, pin in enumerate(spaced_top, start=1):
            if pin:
                # memorize position to later put component value here
                last_top_x = ((box_width - top_width)//100//2 + i)*100
                drawing.append(pin.draw(pin_length, 'down',
                                        x=last_top_x, y=box_height+pin_length))

        for i, pin in enumerate(spaced_bottom, start=1):
            if pin:
                x = ((box_width - bottom_width)//100//2 + i)*100
                drawing.append(pin.draw(pin_length, 'up', x=x, y=-pin_length))

                if pin.graphical_type == 'vss':
                    for stacked in stacked_vss[pin.name][1:]:
                        drawing.append(stacked.draw(pin_length, 'up', x=x, y=-pin_length,
                                                    visible=False))

        for i, pin in enumerate(pins['nc']):
            if pin:
                # x=0 because of https://klc.kicad.org/symbol/s4/s4.6/
                drawing.append(pin.draw(pin_length, 'right', x=0, y=i*100,
                                        visible=False))

        # Center the symbol
        cx, cy = -math.floor(box_width / 2 / 100) * 100, -math.floor(box_height / 2 / 100) * 100
        drawing.translate(Point(cx, cy))

        property = self.symbol.get_property("Reference")
        property.set_pos_mil(cx, cy + box_height + 50, 0)
        property.effects.h_justify = "left"

        property = self.symbol.get_property("Value")
        property.set_pos_mil(cx+last_top_x+100, cy+box_height+50, 0)
        property.effects.h_justify = "left"

        property = self.symbol.get_property("Footprint")
        property.set_pos_mil(cx, cy, 0)
        property.effects.h_justify = "right"
        property.effects.is_hidden = True

        drawing.appendToSymbol(self.symbol)


@click.command()
@click.option('--part-number', '-p', 'part_number_pattern', default='*',
              help='Filter part numbers by glob')
@click.option('--verify-datasheets/--no-verify-datasheets',
              help='Verify datasheet URLs exists')
@click.option('--skip-without-footprint/--keep-without-footprint', default=False,
              help='Skip generating symbols for which no footprint could be found')
@click.option('--skip-without-datasheet/--keep-without-datasheet', default=False,
              help='Skip generating symbols for which no datasheet could be found')
@click.option('--url-cache', type=click.Path(file_okay=True, dir_okay=False,
                                             path_type=pathlib.Path),
              help='JSON cache file for datasheet URLs')
@click.argument('cubemx_mcu_db_dir', type=click.Path(file_okay=False, dir_okay=True,
                                                     path_type=pathlib.Path))
@click.argument('output_file', type=click.Path(file_okay=True, dir_okay=False))
def cli(cubemx_mcu_db_dir, part_number_pattern, output_file, verify_datasheets, url_cache,
        skip_without_footprint, skip_without_datasheet):
    soup = BeautifulSoup((cubemx_mcu_db_dir / 'families.xml').read_text(), features='xml')
    files = defaultdict(lambda: [])
    for tag in soup.find_all('Mcu', recursive=True):
        if not fnmatch.fnmatch(tag['RPN'].lower(), part_number_pattern.lower()):
            continue

        # Parse information for documentation
        frequency = tag.find("Frequency")
        frequency = f'{frequency.text} MHz, ' if frequency else ''
        ram = int(tag.find('Ram').text)
        flash = int(tag.find('Flash').text)
        io = int(tag.find('IONb').text)
        voltage = tag.find('Voltage')
        voltage = f'{voltage["Min"]}-{voltage["Max"]}V, ' if voltage else ''
        refname = tag['RefName']
        package = tag['PackageName']
        core = tag.find('Core').text

        # Make strings for DCM entries
        desc = (
            f"STMicroelectronics {core} MCU, {{flash}}KB flash, "
            f"{{ram}}KB RAM, {frequency}{voltage}{io} GPIO, {{package}}"
        )
        keywords = f'{tag.find("Core").text} {tag.parent.parent["Name"]} {tag.parent["Name"]}'
        datasheet = f'https://www.st.com/resource/en/datasheet/{tag["RPN"].lower()}.pdf'

        files[tag['Name']].append((desc, keywords, datasheet, flash, ram, refname, package))

    print(f'Found {sum(len(e) for e in files)} part variants.')
    print('Generating symbols...')

    lib = kicad_sym.KicadLibrary(output_file)

    if url_cache:
        url_cache = sqlite3.connect(url_cache)
    else:
        url_cache = sqlite3.connect(':memory:')

    url_cache.execute('CREATE TABLE IF NOT EXISTS urls (computed_url, actual_url, timestamp, response)')

    def verify_datasheet(datasheet):
        if not verify_datasheets:
            return datasheet

        with url_cache as cur:
            res = cur.execute('''SELECT response, actual_url FROM urls
                                 WHERE computed_url=? AND timestamp > datetime("now", "-90 day")
                                 ORDER BY timestamp DESC LIMIT 1''', (datasheet,)).fetchone()

            if res:
                code, url = res
                if code == 200:
                    return url
                else:
                    return ''

            client = httpx.Client(http2=True)
            ua_headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/114.0',
                'From': 'kicad-libraries@jaseg.de',
                }
            try:
                res = client.head(datasheet, follow_redirects=True, headers=ua_headers)
                cur.execute('INSERT INTO urls VALUES (?, ?, datetime(), ?)', (datasheet, datasheet, res.status_code))

                if res.status_code == 200:
                    return datasheet

            except httpx.ReadTimeout:
                res = None
                cur.execute('INSERT INTO urls VALUES (?, ?, datetime(), 0)', (datasheet, datasheet))

            # For most parts, the computed part numbers above work just fine. For some parts however, the filename is
            # not the complete RPN, but instead a shorter prefix of it. In case the request above was answered 404 not
            # found, retry with a truncated part number. If that still doesn't work, we give up.
            for cutoff in [-5, -6]:
                if res and res.status_code != 404:
                    break

                # try cutting off one letter from the part number
                testurl = datasheet[:cutoff] + '.pdf'

                try:
                    res = client.head(testurl, follow_redirects=True, headers=ua_headers)
                    cur.execute('INSERT INTO urls VALUES (?, ?, datetime(), ?)', (datasheet, testurl, res.status_code))

                    if res.status_code == 200:
                        tqdm.tqdm.write(f'Datasheet for {refname} unexpectedly found at {testurl} instead '
                                        f'of {datasheet}')
                        return testurl

                except httpx.ReadTimeout:
                    res = None
                    cur.execute('INSERT INTO urls VALUES (?, ?, datetime(), 0)', (datasheet, datasheet))

            if res:
                tqdm.tqdm.write(f'Datasheet for {refname} not found at {datasheet} '
                                f'(Status code {res.status_code})')

            else:
                tqdm.tqdm.write(f'Datasheet for {refname} not found at {datasheet} '
                                f'(HTTP/2 request timeout)')
            return ''

    for filename, variants in tqdm.tqdm(files.items(), desc=pathlib.Path(output_file).stem):
        xml = cubemx_mcu_db_dir / f'{filename}.xml'

        desc, keywords, datasheet, flash, ram, _refname, package = variants[0]
        datasheet = verify_datasheet(datasheet)

        if len(variants) == 1:
            desc = desc.format(flash=flash, ram=ram, package=package)
        else:
            flashes = [flash for _desc, _keywords, _datasheet, flash, _ram, _refname, _package
                       in variants]
            ramses = [ram for _desc, _keywords, _datasheet, _flash, ram, _refname, _package
                      in variants]
            packages = '/'.join(sorted(set(package
                                for _desc, _keywords, _datasheet, _flash, _ram, _refname, package
                                in variants)))
            minf, maxf = min(flashes), max(flashes)
            minr, maxr = min(ramses), max(ramses)
            desc = desc.format(package=packages,
                               flash=f'{minf}-{maxf}' if minf != maxf else str(minf),
                               ram=f'{minr}-{maxr}' if minr != maxr else str(minr))

        dev = Device(xml)

        if skip_without_footprint and not dev.footprint:
            tqdm.tqdm.write(f'No footprint for device {dev.name} with ST package name {dev.package}, skipping.')
            continue

        if skip_without_datasheet and not datasheet:
            tqdm.tqdm.write(f'No datasheet for device {dev.name}, skipping.')
            continue

        dev.create_symbol(lib, keywords=keywords, desc=desc, datasheet=datasheet)

        if len(variants) > 1:
            for desc, keywords, datasheet, flash, ram, refname, package in variants:
                desc = desc.format(flash=flash, ram=ram, package=package)

                derived_symbol = kicad_sym.KicadSymbol.new(
                    refname, lib.filename, "U", dev.footprint,
                    datasheet, keywords, desc,
                    dev.footprint_filters,
                )

                derived_symbol.extends = dev.name

                def clone_formatting(dest, src, name):
                    src, dest = src.get_property(name), dest.get_property(name)
                    dest.posx = src.posx
                    dest.posy = src.posy
                    dest.effects = src.effects

                clone_formatting(derived_symbol, dev.symbol, 'Reference')
                clone_formatting(derived_symbol, dev.symbol, 'Value')
                clone_formatting(derived_symbol, dev.symbol, 'Footprint')

                lib.symbols.append(derived_symbol)

    now = time.time()
    lib.write()
    after = time.time()
    print(f'Wrote library file in {after-now:.6f} s')


if __name__ == "__main__":
    cli()
