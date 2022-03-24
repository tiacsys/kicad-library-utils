# -*- coding: utf-8 -*-

from rules_symbol.rule import *
import re


class Rule(KLCRule):
    """Pin electrical type should match pin function"""

    # Power Input Pins should be 'W'
    POWER_INPUTS = ['^[ad]*g(rou)*nd(a)*$', '^[ad]*v(aa|cc|dd|ss|bat|in)$']

    # Power Output Pins should be 'w'
    POWER_OUTPUTS = ['^vout$']

    PASSIVE_PINS = []

    # Input Pins should be "I"
    INPUT_PINS = ['^sdi$', '^cl(oc)*k(in)*$', '^~*cs~*$', '^[av]ref$']

    # Output pins should be "O"
    OUTPUT_PINS = ['^sdo$', '^cl(oc)*kout$']

    # Bidirectional pins should be "B"
    BIDIR_PINS = ['^sda$', '^s*dio$']

    warning_tests = {
        "power_out": POWER_OUTPUTS,
        "passive": PASSIVE_PINS,
        "input": INPUT_PINS,
        "output": OUTPUT_PINS,
        "bidirectional": BIDIR_PINS,
        }

    def __init__(self, component):
        super().__init__(component)

        self.power_errors = []
        self.suggestions = []
        self.inversion_errors = []

    # check if a pin name fits within a list of possible pins (using regex testing)
    def test(self, pinName, nameList):
        for name in nameList:
            if re.search(name, pinName, flags=re.IGNORECASE) is not None:
                return True
        return False


    # These pin types must be satisfied
    def checkPowerPins(self):
        self.power_errors = []

        for stack in self.component.get_pinstacks().values():
            visible = [pin for pin in stack if pin.is_hidden == False]
            invisible = [pin for pin in stack if pin.is_hidden == True]
            # Due to the implementation of S4.3 it is possible to assume that at maximum one pin is visible
            if visible:
                checkpins = [visible[0]]
            else:
                checkpins = invisible
            for pin in checkpins:
                name = pin.name.lower()
                etype = pin.etype

                if self.test(name.lower(), self.POWER_INPUTS) and (not etype.lower() == 'power_in'):
                    if len(self.power_errors) == 0:
                        self.error("Power pins should be of type POWER INPUT or POWER OUTPUT")
                    self.power_errors.append(pin)
                    self.errorExtra("{pin} is of type {t}".format(
                        pin=pinString(pin),
                      t=etype))

            if len(stack) > 1 and visible and visible[0].etype.lower() == 'power_in':
                for pin in invisible:
                    if pin.etype.lower() != 'passive':
                        if len(self.power_errors) == 0:
                            self.error("Invisible powerpins in stacks should be of type PASSIVE")

        return len(self.power_errors) > 0

    # These pin types are suggestions
    def checkSuggestions(self):
        self.suggestions = []

        for pin in self.component.pins:
            name = pin.name.lower()
            etype = pin.etype

            for pin_type in self.warning_tests.keys():
                pins = self.warning_tests[pin_type]
                tests = self.warning_tests[pin_type]

                if self.test(name, tests):
                    if not pin_type == etype:
                        if len(self.suggestions) == 0:
                            self.warning("Pin types should match pin function")
                        self.suggestions.append(pin)
                        self.warningExtra("{pin} is type {t1} : suggested {t2}".format(
                                        pin=pinString(pin),
                                        t1=etype,
                                        t2=pin_type))

                    break

        # No error generated for this rule
        return False

    def checkDoubleInversions(self):
        self.inversion_errors = []
        for pin in self.component.pins:
            m = re.search('(\~{)(.+)}', pin.name)
            if m and pin.shape == 'inverted':
                if len(self.inversion_errors) == 0:
                    self.error("Pins should not be inverted twice (with inversion-symbol on pin and overline on label)")
                self.inversion_errors.append(pin)
                self.errorExtra("{pin} : double inversion (overline + pin type:Inverting)".format(pin=pinString(pin)))

        return len(self.inversion_errors) > 0

    def check(self):
        # no need to check this for an alias
        if self.component.extends != None:
            return False

        """
        Proceeds the checking of the rule.
        The following variables will be accessible after checking:
            * probably_wrong_pin_types
            * double_inverted_pins
        """

        return any([
            self.checkPowerPins(),
            self.checkDoubleInversions(),
            self.checkSuggestions()
            ])

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        self.info("Fixing...")

        for pin in self.power_errors:

            pin['electrical_type'] = 'W'  # Power Input

            self.info("Changing pin {n} type to POWER_INPUT".format(n=pin['num']))

        for pin in self.inversion_errors:
            pin['pin_type'] = ""  # reset pin type (removes dot at the base of pin)
            self.info("Removing double inversion on pin {n}".format(n=pin['num']))

        self.recheck()
