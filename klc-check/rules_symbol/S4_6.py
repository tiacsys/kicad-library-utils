# -*- coding: utf-8 -*-

from rules_symbol.rule import *
import re


class Rule(KLCRule):
    """Hidden pins"""

    # No-connect pins should be "N"
    NC_PINS = ['^nc$', '^dnc$', '^n\.c\.$']

    # check if a pin name fits within a list of possible pins (using regex testing)
    def test(self, pinName, nameList):
        for name in nameList:
            if re.search(name, pinName, flags=re.IGNORECASE) is not None:
                return True

        return False

    def checkNCPins(self, pins):
        self.invisible_errors = []
        self.type_errors = []

        for pin in pins:
            name = pin.name.lower()
            etype = pin.etype

            # Check NC pins
            if self.test(name, self.NC_PINS) or etype == 'no_connect':
                # NC pins should be of type no_connect
                if not etype == 'no_connect':  # Not set to NC
                    self.type_errors.append(pin)

                # NC pins should be invisible
                if pin.is_hidden == False:
                    self.invisible_errors.append(pin)

        if len(self.type_errors) > 0:
            self.error("NC pins are not correct pin-type:")

            for pin in self.type_errors:
                self.errorExtra("{pin} should be of type NOT CONNECTED, but is of type {pintype}".format(
                    pin=pinString(pin),
                    pintype=etype))

        if len(self.invisible_errors) > 0:
            self.warning("NC pins are VISIBLE (should be INVISIBLE):")

            for pin in self.invisible_errors:
                self.warningExtra("{pin} should be INVISIBLE".format(pin=pinString(pin)))

        return len(self.invisible_errors) > 0 or len(self.type_errors) > 0

    def check(self):
        """
        Proceeds the checking of the rule.
        The following variables will be accessible after checking:
            * probably_wrong_pin_types
            * double_inverted_pins
        """
        # no need to check this for an alias
        if self.component.extends != None:
            return False


        fail = False

        if self.checkNCPins(self.component.pins):
            fail = True

        return fail

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        self.info("Fixing...")

        for pin in self.invisible_errors:
            if not pin.is_hidden == True:
                pin.is_hidden = True
                self.info("Setting pin {n} to INVISIBLE".format(n=pin.number))

        for pin in self.type_errors:
            if not pin.etype == 'no_connect':
                pin.etype = 'no_connect'
                self.info("Changing pin {n} type to NO_CONNECT".format(n=pin.number))

        self.recheck()
