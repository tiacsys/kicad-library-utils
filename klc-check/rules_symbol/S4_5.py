# -*- coding: utf-8 -*-

from rules_symbol.rule import *


class Rule(KLCRule):
    """Pins not connected on the footprint may be omitted from the symbol"""

    def checkMissingPins(self):
        int_pins = []
        for pin in self.component.pins:
            try:
                int_pins.append(int(pin.number))
            except:
                pass

        if len(int_pins) == 0:
            return False

        missing_pins = []
        for i in range(1, max(int_pins) + 1):
            if i not in int_pins:
                missing_pins.append(i)
        if len(missing_pins) != 0:
            self.warning("Pin{s} {n} {v} missing.".format(
                         s="s" if len(missing_pins) > 1 else "",
                         n=", ".join(str(x) for x in missing_pins),
                         v="are" if len(missing_pins) > 1 else "is"))
        return False

    def check(self):
        # no need to check pins on an alias
        if self.component.extends != None:
            return False

        return self.checkMissingPins()

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """

        self.info("Fix not supported")
