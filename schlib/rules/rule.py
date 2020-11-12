# -*- coding: utf-8 -*-

import sys
import os

common = os.path.abspath(os.path.join(sys.path[0], '..', 'common'))

if common not in sys.path:
    sys.path.append(common)

from rulebase import *

def mil_to_mm(mil):
    return round(mil * 0.0254, 6)

def mm_to_mil(mm):
    return round(mm / 0.0254)

def pinString(pin, loc=True, unit=None, convert=None):
    return "Pin {name} ({num}){loc}{unit}".format(
        name=pin.name,
        num=pin.number,
        loc=' @ ({x},{y})'.format(x=mm_to_mil(pin.posx), y=mm_to_mil(pin.posy)) if loc else '',
        unit=' in unit {n}'.format(n=pin.unit) if unit else '')


def positionFormater(element):
    if type(element) == type({}):
        if(not {"posx", "posy"}.issubset(element.keys())):
            raise Exception("missing keys 'posx' and 'posy' in"+str(element))
        return "@ ({0}, {1})".format(mm_to_mil(element['posx']), mm_to_mil(element['posy']))
    if 'posx' in element.__dict__ and 'posy' in element.__dict__:
        return "@ ({0}, {1})".format(mm_to_mil(element.posx), mm_to_mil(element.posy))
    raise Exception("input type: ", type(element), "not supported, ", element)


class KLCRule(KLCRuleBase):
    """A base class to represent a KLC rule

    Create the methods check and fix to use with the kicad lib files.
    """
    verbosity = 0

    def __init__(self, component):
        KLCRuleBase.__init__(self)
        self.component = component
