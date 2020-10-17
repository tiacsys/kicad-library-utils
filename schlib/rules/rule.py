# -*- coding: utf-8 -*-

import sys
import os

common = os.path.abspath(os.path.join(sys.path[0], '..', 'common'))

if common not in sys.path:
    sys.path.append(common)

from rulebase import *


# this should go to separate file
def pinElectricalTypeToStr(pinEType):
    pinMap = {"I": "INPUT",
    "O": "OUTPUT",
    "B": "BIDI",
    "T": "TRISTATE",
    "P": "PASSIVE",
    "U": "UNSPECIFIED",
    "W": "POWER INPUT",
    "w": "POWER OUTPUT",
    "C": "OPEN COLLECTOR",
    "E": "OPEN EMITTER",
    "N": "NOT CONNECTED"}
    if pinEType in pinMap.keys():
        return pinMap[pinEType]
    else:
        return "INVALID"


def pinTypeToStr(pinType):
    pinMap = {"I": "INVERTED",
    "C": "CLOCK",
    "CI": "INVERTED CLOCK",
    "L": "INPUT LOW",
    "CL": "CLOCK LOW",
    "V": "OUTPUT LOW",
    "F": "FALLING EDGE CLOCK",
    "X": "NON LOGIC"}
    if pinType in pinMap.keys():
        return pinMap[pinType]
    else:
        return "INVALID"


def backgroundFillToStr(bgFill):
    bgMap = {
    "F": "FOREGROUND",
    "f": "BACKGROUND",
    "N": "TRANSPARENT"}
    if bgFill in bgMap.keys():
        return bgMap[bgFill]
    else:
        return "INVALID"


def pinString(pin, loc=True, unit=None, convert=None):
    return "Pin {name} ({num}){loc}{unit}".format(
        name=pin['name'],
        num=pin['number'],
        loc=' @ ({x},{y})'.format(x=pin['posx'], y=pin['posy']) if loc else '',
        unit=' in unit {n}'.format(n=unit) if unit else '')


def positionFormater(element):
    if type(element) != type({}):
        raise Exception("input type: ", type(element), "expected dictionary, ", element)
    if(not {"posx", "posy"}.issubset(element.keys())):
        raise Exception("missing keys 'posx' and 'posy' in"+str(element))
    return "@ ({0}, {1})".format(element['posx'], element['posy'])
    # return "pos [{0},{1}]".format(element['posx'],element['posy'])


class KLCRule(KLCRuleBase):
    """
    A base class to represent a KLC rule
    """

    verbosity = 0
    v6 = False

    def __init__(self, component, description):
        KLCRuleBase.__init__(self, description)
        self.component = component

    def mil_to_mm(self, mil):
      return mil * 0.0254

    def mm_to_mil(self, mm):
      return round(mm / 0.0254)
