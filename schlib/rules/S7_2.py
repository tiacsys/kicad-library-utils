# -*- coding: utf-8 -*-

from rules.rule import *
import re


class Rule(KLCRule):
    """
    Create the methods check and fix to use with the kicad lib files.
    """
    v6 = True
    def __init__(self, component):
        super(Rule, self).__init__(component, 'Graphical symbols follow some special rules/KLC-exceptions')
        self.fixTooManyPins = False
        self.fixNoFootprint = False

    def check(self):
        """
        Proceeds the checking of the rule.
        """

        fail = False
        if self.component.is_graphic_symbol():
            # no pins in raphical symbol
            if (len(self.component.pins) != 0):
                self.error("Graphical symbols have no pins")
                fail = True
                self.fixTooManyPins = True
            # footprint field must be empty
            fp_prop = self.component.get_property("Footprint")
            if fp_prop and fp_prop.value != '':
                self.error("Graphical symbols have no footprint association (footprint was set to '"+self.component.fields[2]['name']+"')")
                fail = True
                self.fixNoFootprint = True
            # FPFilters must be empty
            if len(self.component.get_fp_filters()) > 0:
                self.error("Graphical symbols have no footprint filters")
                fail = True
                self.fixNoFootprint = True

        return fail

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        if self.fixTooManyPins:
            self.info("FIX for too many pins in graphical symbol")
            self.component.pins = []
        if self.fixNoFootprint:
            self.info("FIX empty footprint association and FPFilters")
            self.component.get_property("Footprint").value = ""
            self.component.get_property("ki_fp_filters").value = ""
