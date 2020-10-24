# -*- coding: utf-8 -*-

from rules.rule import *


class Rule(KLCRule):
    """
    Create the methods check and fix to use with the kicad lib files.
    """
    v6 = True
    def __init__(self, component):
        super(Rule, self).__init__(component, 'Pin requirements')

    def checkMissingPins(self):
        int_pins = []
        for pin in self.component.pins:
            try:
                int_pins.append(int(pin.number))
            except:
                pass

        if len(int_pins) == 0:
            return False

        for i in range(1, max(int_pins) + 1):
            if i not in int_pins:
                self.warning("Pin {n} is missing".format(n=i))
        return False

    def checkPinOrigin(self, gridspacing=100):
        self.violating_pins = []
        err = False
        for pin in self.component.pins:
            posx = mm_to_mil(pin.posx)
            posy = mm_to_mil(pin.posy)
            if (posx % gridspacing) != 0 or (posy % gridspacing) != 0:
                self.violating_pins.append(pin)
                if not err:
                    self.error("Pins not located on {0}mil (={1:.3}mm) grid:".format(gridspacing, gridspacing*0.0254))
                self.error(' - {0} '.format(pinString(pin, loc = True)))
                err = True

        return len(self.violating_pins) > 0

    def checkDuplicatePins(self):
        # look for duplicate pin numbers
        duplicate = False
        test_pins = list(self.component.pins)
        for pin0 in test_pins:
            for pin1 in test_pins:
                if pin0 != pin1 and pin0.is_duplicate(pin1):
                    duplicate = True
                    self.error("Pin {n} is duplicated:".format(n=pin0.number))
                    self.errorExtra(pinString(pin0))
                    test_pins.remove(pin0)
                    test_pins.remove(pin1)

        return duplicate

    def checkPinLength(self, errorPinLength=49, warningPinLength=99):
        self.violating_pins = []

        for pin in self.component.pins:
            length = mm_to_mil(pin.length)

            err = False

            # ignore zero-length pins e.g. hidden power pins
            if length == 0:
                continue

            if length <= errorPinLength:
                self.error("{pin} length ({len}mils) is below {pl}mils".format(pin=pinString(pin), len=length, pl=errorPinLength+1))
            elif length <= warningPinLength:
                self.warning("{pin} length ({len}mils) is below {pl}mils".format(pin=pinString(pin), len=length, pl=warningPinLength+1))

            if length % 50 != 0:
                self.warning("{pin} length ({len}mils) is not a multiple of 50mils".format(pin=pinString(pin), len=length))

            # length too long flags a warning
            if length > 300:
                err = True
                self.error("{pin} length ({length}mils) is longer than maximum (300mils)".format(
                    pin=pinString(pin),
                    length=length))

            if err:
                self.violating_pins.append(pin)

        return len(self.violating_pins) > 0

    def check(self):
        # no need to check pins on an alias
        if self.component.extends != None:
            return False

        # determine pin-grid:
        #  - standard components should use 100mil
        #  - "small" symbols (resistors, diodes, ...) should use 50mil
        pingrid = 100
        errorPinLength = 49
        warningPinLength = 99
        if self.component.is_small_component_heuristics():
            pingrid = 50
            errorPinLength = 24
            warningPinLength = 49

        return any([
            self.checkMissingPins(),
            self.checkPinOrigin(pingrid),
            self.checkPinLength(errorPinLength, warningPinLength),
            self.checkDuplicatePins()
            ])

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """

        self.info("Fix not supported")

        if self.checkPinOrigin():
            pass

        if self.checkPinLength():
            pass
