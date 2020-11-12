#!/usr/bin/env python
# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import List

import re, math
import sys, os
common = os.path.abspath(os.path.join(sys.path[0], '..','common'))
if not common in sys.path:
    sys.path.append(common)

import sexpr
import pprint
import json


def _parse_at(i):
    sexpr_at = _get_array(i, 'at')[0]
    posx = sexpr_at[1]
    posy = sexpr_at[2]
    if len(sexpr_at) == 4:
      rot = sexpr_at[3]
    else:
      rot = None
    return (posx, posy, rot)

def _get_array(data, value, result=None, level=0, max_level=None):
    """return the array which has value as first element"""
    if result is None: result = []

    if max_level is not None and max_level <= level:
        return result

    level += 1

    for i in data:
        if type(i) == type([]):
            _get_array(i, value, result, level=level, max_level=max_level)
        else:
            if i == value:
                result.append(data)
    return result

def _get_array2(data, value):
    ret = []
    for i in data:
        if type(i) == type([]) and i[0] == value:
            ret.append(i)
    return ret

def _get_color(sexpr):
    col = None
    for i in sexpr:
        if type(i) == type([]) and i[0] == 'color':
            col = Color(i[1], i[2], i[3], i[4])
    return col


def _get_stroke(sexpr):
    width = None
    col = None
    for i in sexpr:
        if type(i) == type([]) and i[0] == 'stroke':
            width = _get_value_of(i, 'width')
            col = _get_color(i)
            break
    return (width, col)

def _get_fill(sexpr):
    fill = None
    col = None
    for i in sexpr:
        if type(i) == type([]) and i[0] == 'fill':
            fill = _get_value_of(i, 'type')
            col = _get_color(i)
            break
    return (fill, col)

def _get_xy(sexpr, lookup):
    for i in sexpr:
        if type(i) == type([]) and i[0] == lookup:
            return (i[1], i[2])
    return (0, 0)

def _get_value_ofRecursively(data, path, item_to_get=False):
    """return the array which has value as first element, but recursively

        if item_to_get is != 0, return the array element with that index
    """
    # if we walked the whole path we are done. return the data
    if len(path) == 0:
        # in some cases it is usefull to only get the 2nd item, for
        # example ['lenght', 42] should just return 42
        if item_to_get != 0:
            return data[item_to_get]
        return data

    for i in data:
        # look at sub-arrays, if their first element matches the path-spec,
        # strip the front item from the path list and do this recursively
        if type(i) == type([]) and i[0] == path[0]:
            return _get_value_ofRecursively(i, path[1:], item_to_get)

def _get_value_of(data, lookup, default=None):
    """find the array which has lookup as first element, return its 2nd element"""
    for i in data:
        if type(i) == type([]) and i[0] == lookup:
            return i[1]
    return default

def _has_value(data, lookup):
    """return true if the lookup item exists"""
    for i in data:
        if type(i) == type([]) and i[0] == lookup:
            return True
    return False

class KicadSymbolBase(object):
    def as_json(self):
      return json.dumps(self, default=lambda x: x.__dict__, indent=2)

    def compare_pos(s, x, y):
        if 'posx' in s.__dict__ and 'posy' in s.__dict__:
            return round(s.posx, 6) == round(x, 6) and round(s.posy, 6) == round(y, 6)
        return False

    @classmethod
    def dir_to_rotation(cls, d):
       if d == 'R':
           return 0
       if d == 'U':
           return 90
       if d == 'L':
           return 180
       if d == 'D':
           return 270

@dataclass
class Color(KicadSymbolBase):
    """Encode the color of an entiry. Currently not used in the kicad_sym format"""
    r: int
    g: int
    b: int
    a: int

@dataclass
class TextEffect(KicadSymbolBase):
    """Encode the text effect of an entiry"""
    sizex: float
    sizey: float
    is_italic: bool = False
    is_bold: bool = False
    is_hidden: bool = False
    is_mirrored: bool = False
    h_justify: str = "center"
    v_justify: str = "center"
    color: Color = None
    font: str = None

    def get_sexpr(s):
      sx = ['effects']
      font = ['font', ['size', s.sizex, s.sizey]]
      if s.is_italic: font.append('italic') 
      if s.is_bold: font.append('bold') 
      if s.is_mirrored: font.append('mirror') 
      if s.color: font.append(s.color.get_sexpr())
      if s.is_hidden: font.append('hidden') 
      sx.append(font)

      justify = ['justify']
      if s.h_justify: justify.append(s.h_justify)
      if s.v_justify: justify.append(s.v_justify)
 
      if len(justify) > 1: sx.append(justify)
      return sx
  
    @classmethod
    def from_sexpr(cls, sexpr):
        sexpr_orig = sexpr.copy()
        if (sexpr.pop(0) != 'effects'):
            return None
        font = _get_array(sexpr, 'font')[0]
        (sizex, sizey) = _get_xy(font, 'size')
        is_italic = 'italic' in sexpr
        is_bold = 'bold' in sexpr
        is_hidden = 'hide' in sexpr
        is_mirrored = 'mirror' in sexpr
        justify = _get_array2(sexpr, 'justify')
        h_justify = "center"
        v_justify = "center"
        if justify:
            if 'top' in justify[0]: v_justify = 'top'
            if 'bottom' in justify[0]: v_justify = 'bottom'
            if 'left' in justify[0]: h_justify = 'left'
            if 'right' in justify[0]: h_justify = 'right'
        return TextEffect(sizex, sizey, is_italic, is_bold, is_hidden, is_mirrored, h_justify, v_justify)

@dataclass
class Pin(KicadSymbolBase):
    name: str
    name_effect: TextEffect
    number: str
    number_int: int
    number_effect: TextEffect
    posx: float
    posy: float
    rotation: int
    etype: str
    shape: str
    length: float
    unit: int = 0
    demorgan: int = 0
    is_global: bool = False
    is_hidden: bool = False
    #sexpr: any = field(default=None, repr=False)

    @classmethod
    def _parse_name_or_number(cls, i, typ='name'):
        """ Convert a sexpr pin-name or pin-number into a python dict """
        sexpr_n = _get_array(i, typ)[0]
        name = sexpr_n[1]
        effects = TextEffect.from_sexpr(_get_array(sexpr_n, 'effects')[0])
        return (name, effects)

    def get_sexpr(s):
        sx = [
            'pin', s.etype, s.shape, ['at', s.posx, s.posy, s.rotation],
            ['length', s.length], ['name', s.name], ['number', s.number]
        ]
        return sx

    def get_direction(s):
       if s.rotation == 0:
         return 'R'
       elif s.rotation == 90:
         return 'U'
       elif s.rotation == 180:
         return 'L'
       elif s.rotation == 270:
         return 'D'

    def is_duplicate(s, p):
       if p.number == s.number and p.unit == s.unit and p.demorgan == s.demorgan:
           return True

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        # TODO: Texts
        is_global = False
        # The first 3 items are pin, type and shape
        if (sexpr.pop(0) != 'pin'):
            return None
        etype = sexpr.pop(0)
        shape = sexpr.pop(0)
        # the 4th item (global) is optional
        if sexpr[0] == 'global':
            sexpr.pop(0)
            is_global = True
        # fetch more properties
        is_hidden = 'hide' in sexpr
        length = _get_value_of(sexpr, 'length')
        (posx, posy, rotation) = _parse_at(sexpr)
        (name, name_effect) = cls._parse_name_or_number(sexpr)
        (number, number_effect) = cls._parse_name_or_number(sexpr, typ='number')
        # we also need the pin-number as integer, try to convert it.
        # Some pins won't work since they are called 'MP' or similar
        number_int = None
        try:
            number_int = int(number)
        except ValueError:
            pass
        # create and return a pin with the just extraced values
        return Pin(name,
                   name_effect,
                   number,
                   number_int,
                   number_effect,
                   posx,
                   posy,
                   rotation,
                   etype,
                   shape,
                   length,
                   unit = unit,
                   is_hidden=is_hidden,
                   is_global=is_global)

@dataclass
class Circle(KicadSymbolBase):
    centerx: float
    centery: float
    radius: float
    stroke_width: float
    stroke_color: Color
    fill_type: str
    fill_color: Color
    unit: int = 0
    demorgan: int = 0

    def get_sexpr(s):
        sx = [
            'circle', ['center', s.centerx, s.centery], ['radius', s.radius],
            ['stroke', ['width', s.stroke_width]],
            ['fill', ['type', s.fill_type]]
        ]
        return sx

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        # The first 3 items are pin, type and shape
        if (sexpr.pop(0) != 'circle'):
            return None
        # the 1st element
        (centerx, centery) = _get_xy(sexpr, 'center')
        radius = _get_value_of(sexpr, 'radius')
        (stroke, scolor) = _get_stroke(sexpr)
        (fill, fcolor) = _get_fill(sexpr)
        return Circle(centerx, centery, radius, stroke, scolor, fill, fcolor, unit = unit)

@dataclass
class Arc(KicadSymbolBase):
    # (arc (start 2.54 12.7) (end 12.7 5.08) (radius (at 3.81 3.81) (length 8.9803) (angles 98.1 8.1))
    startx: float
    starty: float
    endx: float
    endy: float
    centerx: float
    centery: float
    length: float
    angle_start: float
    angle_stop: float
    stroke_width: float
    stroke_color: Color
    fill_type: str
    fill_color: Color
    unit: int = 0
    demorgan: int = 0

    def get_sexpr(s):
        sx = [
            'arc', ['start', s.startx, s.starty], ['end', s.endy, s.endy],
            ['radius', ['at', centerx, centery], ['length', s.length],
            ['angles', s.angle_start, s.angle_stop]],
            ['stroke', ['width', s.stroke_width]],
            ['fill', ['type', s.fill_type]]
        ]
        return sx

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        if (sexpr.pop(0) != 'arc'):
            return None
        # the 1st element
        (startx, starty) = _get_xy(sexpr, 'start')
        (endx, endy) = _get_xy(sexpr, 'end')
        rad = _get_array(sexpr, 'radius')[0]
        (centerx, centery) = _get_xy(rad, 'at')
        length = _get_value_of(rad, 'length')
        (angle_start, angle_stop) = _get_xy(rad, 'angles')
        (stroke, scolor) = _get_stroke(sexpr)
        (fill, fcolor) = _get_fill(sexpr)
        return Arc(startx, starty, endx, endy, centerx, centery, length, angle_start, angle_stop, stroke, scolor, fill, fcolor, unit=unit)

@dataclass
class Point(KicadSymbolBase):
    x: float
    y: float
    def get_sexpr(s):
      return ['xy', s.x, s.y]

@dataclass
class Polyline(KicadSymbolBase):
    pts: List[Point]
    stroke_width: float
    stroke_color: Color
    fill_type: str
    fill_color: Color
    unit: int = 0
    demorgan: int = 0

    def get_sexpr(s):
        pts_list = list(map(lambda x: x.get_sexpr(), s.pts))
        pts_list.insert(0, 'pts')
        sx = [
            'polyline', pts_list,
            ['stroke', ['width', s.stroke_width]],
            ['fill', ['type', s.fill_type]]
        ]
        return sx

    def is_closed(s):
        # if the last and first point are the same, we consider the polyline closed
        # a closed triangle will have 4 points (A-B-C-A) stored in the list of points
        return len(s.pts) > 3 and s.pts[0].__eq__(s.pts[-1])

    def get_boundingbox(s):
        (minx, maxx, miny, maxy) = (0, 0, 0, 0)
        for p in s.pts:
            minx = min(minx, p.x)
            maxx = max(maxx, p.x)
            miny = min(miny, p.y)
            maxy = max(maxy, p.y)
        return(maxx, maxy, minx, miny)

    def get_center_of_boundingbox(s):
        (maxx, maxy, minx, miny) = s.get_boundingbox()
        return ((minx + maxx) / 2, ((miny + maxy) / 2))

    def is_rectangle(s):
        # a rectangle has 5 points and is closed
        if len(s.pts) != 5 or not s.is_closed():
            return False

        # construct lines between the points
        p0 = s.pts[0]
        for p1_idx in range(1, len(s.pts)):
            p1 = s.pts[p1_idx]
            dx = p1.x - p0.x
            dy = p1.y - p0.y
            if dx != 0 and dy != 0:
                # if a line is neither horizontal or vertical its not
                # part of a rectangle
                return False
            # select next point
            p0 = p1

        return True

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        pts = []
        if (sexpr.pop(0) != 'polyline'):
            return None
        for p in _get_array(sexpr, 'pts')[0]:
            if 'xy' in p:
              pts.append(Point(p[1], p[2]))

        (stroke, scolor) = _get_stroke(sexpr)
        (fill, fcolor) = _get_fill(sexpr)
        return Polyline(pts, stroke, scolor, fill, fcolor, unit=unit)

@dataclass
class Text(KicadSymbolBase):
    text: str
    posx: float
    posy: float
    rotation: float
    effects: TextEffect
    unit: int = 0
    demorgan: int = 0

    def get_sexpr(s):
        sx = [
            'text', s.text,
            ['at', [s.posx, s.posy, s.rotation]],
            s.effects.get_sexpr()
        ]
        return sx

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        pts = []
        if (sexpr.pop(0) != 'text'):
            return None
        text = sexpr.pop(0)
        (posx, posy, rotation) = _parse_at(sexpr)
        effects = TextEffect.from_sexpr(_get_array(sexpr, 'effects')[0])
        return Text(text, posx, posy, rotation, effects, unit = unit)

@dataclass
class Rectangle(KicadSymbolBase):
    """Some v6 symbols use rectangles, newer ones encode them as polylines.
       At some point in time we can most likely remove this class since its not used anymore"""
    startx: float
    starty: float
    endx: float
    endy: float
    stroke_width: float
    stroke_color: Color
    fill_type: str
    fill_color: Color
    unit: int = 0
    demorgan: int = 0

    def get_sexpr(s):
        sx = [
            'rectangle', ['start', s.startx, s.starty], ['end', s.endy, s.endy],
            ['stroke', ['width', s.stroke_width]],
            ['fill', ['type', s.fill_type]]
        ]
        return sx

    def as_polyline(s):
        pts = [
            Point(s.startx, s.starty),
            Point(s.endx, s.starty),
            Point(s.endx, s.endy),
            Point(s.startx, s.endy),
            Point(s.startx, s.starty),
        ]
        return Polyline(pts, s.stroke_width, s.stroke_color, s.fill_type, s.fill_color, unit=s.unit)

    def get_center(s):
        x = (s.endx + s.startx)  / 2
        y = (s.endy + s.starty) / 2
        return (x, y)

    @classmethod
    def from_sexpr(cls, sexpr, unit):
        sexpr_orig = sexpr.copy()
        if (sexpr.pop(0) != 'rectangle'):
            return None
        # the 1st element
        (startx, starty) = _get_xy(sexpr, 'start')
        (endx, endy) = _get_xy(sexpr, 'end')
        (stroke, scolor) = _get_stroke(sexpr)
        (fill, fcolor) = _get_fill(sexpr)
        return Rectangle(startx, starty, endx, endy, stroke, scolor, fill, fcolor, unit=unit)

@dataclass
class Property(KicadSymbolBase):
    name: str
    value: str
    idd: int
    posx: float
    posy: float
    rotation: float
    effects: TextEffect
    
    def get_sexpr(s):
        sx = [
            'property', s.name, s.value, ['id', s.idd],
            ['at', [s.posx, s.posy, s.rotation]],
            s.effects.get_sexpr()
        ]
        return sx

    @classmethod
    def from_sexpr(cls, sexpr, unit=0):
        sexpr_orig = sexpr.copy()
        if (sexpr.pop(0) != 'property'):
            return None
        name = sexpr.pop(0)
        value = sexpr.pop(0)
        idd = _get_value_of(sexpr, 'id')
        (posx, posy, rotation) = _parse_at(sexpr)
        effects = TextEffect.from_sexpr(_get_array(sexpr, 'effects')[0])
        return Property(name, value, idd, posx, posy, rotation, effects)

@dataclass
class KicadSymbol(KicadSymbolBase):
    name: str
    libname: str
    filename: str = field(compare=False)
    properties: List[Property] = field(default_factory=list)
    pins: List[Pin] = field(default_factory=list)
    circles: List[Circle] = field(default_factory=list)
    arcs: List[Arc] = field(default_factory=list)
    polylines: List[Polyline] = field(default_factory=list)
    texts: List[Text] = field(default_factory=list)
    pin_names_offset: float = 0.508
    hide_pin_names: bool = False
    hide_pin_numbers: bool = False
    is_power: bool = False
    in_bom: bool = False
    on_board: bool = False
    extends: str = None
    unit_count: int = 0
    demorgan_count: int = 0

    def get_center_rectangle(s, units: List):
        # return a polyline for the requested unit that is a rectangle
        # and is closest to the center
        candidates = {}
        # building a dict with floats as keys.. there needs to be a rule against that^^
        for pl in s.polylines:
          if pl.unit in units and pl.is_rectangle():
            # extract the center, calculate the distance to origin
            (x, y) = pl.get_center_of_boundingbox()
            dist = math.sqrt(x*x + y*y)
            candidates[dist] = pl

        if len(candidates) > 0:
            # sort the list return the first (smalles) item
            return candidates[sorted(candidates.keys())[0]]
        return None

    def get_pinstacks(s):
        stacks = {}
        for pin in s.pins:
            # if the unit is 0 that means this pin is common to all units
            unit_list = [pin.unit]
            if pin.unit == 0:
                unit_list = list(range(1, s.unit_count + 1))

            # if the unit is 0 that means this pin is common to all units
            demorgan_list = [pin.demorgan]
            if pin.demorgan == 0:
                demorgan_list = list(range(1, s.demorgan_count + 1))

            # add the pin to the correct stack
            for demorgan in demorgan_list:
                for unit in unit_list:
                    loc = "x{0}_y{1}_u{2}_d{3}".format(pin.posx, pin.posy, unit, demorgan)
                    if loc in stacks:
                        stacks[loc].append(pin)
                    else:
                        stacks[loc] = [pin]
        return stacks

    def get_property(self, pname):
        for p in self.properties:
            if p.name == pname:
                return p
        return None

    def get_fp_filters(self):
        filters = self.get_property('ki_fp_filters')
        if filters:
            return filters.value.split(" ")
        else:
            return []

    def is_graphic_symbol(self):
        return self.extends == None and (len(self.pins) == 0 or self.get_property('Reference').value == '#SYM')

    def is_power_symbol(self):
        return self.is_power

    def is_locked(self):
      return self.get_property('ki_locked') != None

    def does_extend(self):
        return does_extend

    def get_pins_by_name(self, name):
        pins = []
        for pin in self.pins:
            if pin.name == name:
                pins.append(pin)
        return pins

    def get_pins_by_number(self, num):
        for pin in self.pins:
            if pin.num == str(num):
                return pin
        return None

    def filter_pins(self, name=None, direction=None, electrical_type=None):
        pins = []
        for pin in self.pins:
            if ((name and pin.name == name)
                    or (direction and pin.rotation == self.dir_to_rotation(direction))
                    or (electrical_type
                        and pin.etype == electrical_type)):
                pins.append(pin)
        return pins


    # heuristics, which tries to determine whether this is a "small" component (resistor, capacitor, LED, diode, transistor, ...)
    def is_small_component_heuristics(self):
        if len(self.pins) <= 2:
            return True

        filled_rect = self.get_center_rectangle(range(self.unit_count))

        # if there is no filled rectangle as symbol outline and we have 3 or 4 pins, we assume this
        # is a small symbol
        if len(self.pins) >= 3 and len(self.pins) <= 4 and filled_rect == None:
            return True

        return False


@dataclass
class KicadLibrary(KicadSymbolBase):
    """
    A class to parse kicad_sym files format of the KiCad
    """
    filename: str
    symbols: List[KicadSymbol] = field(default_factory=list)
    version: str = ""
    host: str = ""

    @classmethod
    def from_file(cls, filename):
        library = KicadLibrary(filename)

        # read the s-expression data
        f_name = open(filename)
        lines = ''.join(f_name.readlines())

        #i parse s-expr
        sexpr_data = sexpr.parse_sexp(lines)
        sym_list = _get_array(sexpr_data, 'symbol')
        f_name.close()

        # itertate over symbol
        for item in sym_list:
            if item.pop(0) != 'symbol':
              print ('unexpected token in file')
              continue
            name = item.pop(0)
            m0 = re.match(r'^(.*?):(.*)$', name)
            m1 = re.match(r'^.*_(\d+?)_(\d+?)$', name)
            if (m0 is not None):
                # we found a new part, split symbol and libname
                (libname, partname) = (m0.group(1), m0.group(2))
                symbol = KicadSymbol(str(partname), str(libname), filename)

                # extract extends property
                extends = _get_array2(item, 'extends')
                if len(extends) > 0:
                  symbol.extends = extends[0][1]

                # extract properties
                for prop in _get_array(item, 'property'):
                    symbol.properties.append(Property.from_sexpr(prop))

                # get flags
                if _has_value(item, 'in_bom'):
                    symbol.in_bom = True
                if _has_value(item, 'power'):
                    symbol.is_power = True
                if _has_value(item, 'on_board'):
                    symbol.on_board = True

                # get pin-numbers properties
                pin_numbers_info = _get_array2(item, 'pin_numbers')
                if pin_numbers_info:
                    if 'hide' in pin_numbers_info[0]:
                        symbol.hide_pin_numbers = True

                # get pin-name properties
                pin_names_info = _get_array2(item, 'pin_names')
                if pin_names_info:
                    if 'hide' in pin_names_info[0]:
                        symbol.hide_pin_names = True
                    # sometimes the pin_name_offset value does not exist, then use 20mil as default
                    symbol.pin_names_offset = _get_value_of(pin_names_info[0], 'offset', 0.508)
             
                # add it to the list of symbols
                library.symbols.append(symbol)

            elif (m1 is not None):
                # we found a new 'subpart' (no clue how to call it properly)
                (unit, demorgan) = (m1.group(1), m1.group(2))
                unit = int(unit)
                demorgan = int(demorgan)

                # update the amount of units, alternative-styles (demorgan)
                symbol.unit_count = max(unit, symbol.unit_count)
                symbol.demorgan_count = max(demorgan, symbol.demorgan_count)

                # extract pins and graphical items
                for pin in _get_array(item, 'pin'):
                    symbol.pins.append(Pin.from_sexpr(pin, unit))
                for circle in _get_array(item, 'circle'):
                    symbol.circles.append(Circle.from_sexpr(circle, unit))
                for arc in _get_array(item, 'arc'):
                    symbol.arcs.append(Arc.from_sexpr(arc, unit))
                for rect in _get_array(item, 'rectangle'):
                    symbol.polylines.append(Rectangle.from_sexpr(rect, unit).as_polyline())
                for poly in _get_array(item, 'polyline'):
                    symbol.polylines.append(Polyline.from_sexpr(poly, unit))
                for text in _get_array(item, 'text'):
                    symbol.texts.append(Text.from_sexpr(text, unit))

            else:
                print("could not match entry")
                continue

        return library

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        a = KicadLibrary.from_file(sys.argv[1])
        # debug print the list of symbols
        #print(a)
        print(a.as_json())
    else:
        print("pass a .kicad_sym file please")
