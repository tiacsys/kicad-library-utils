# -*- coding: utf-8 -*-

from rules.rule import *


class Rule(KLCRule):
    """Rules for pin stacking"""

    special_power_pins = ['power_in', 'power_out', 'output']
    different_names = []
    different_types = []
    visible_pin_not_lowest = []
    NC_stacked = []
    non_numeric = []
    more_then_one_visible = False

    def count_pin_etypes(self, pins, etyp):
        n = 0
        for pin in pins:
           if pin.etype == etyp:
               n += 1
        return n

    def get_smallest_pin_number(self, pins):
        min_pin_number = sys.maxsize
        for p in pins:
            if p.number_int != None:
                min_pin_number = min(p.number_int, min_pin_number)
        return min_pin_number

    def check(self):
        # no need to check this for an alias
        if self.component.extends != None:
            return False

        possible_power_pin_stacks = []

        # iterate over pinstacks
        for (pos, pins) in self.component.get_pinstacks().items():
            # skip stacks with only one pin
            if len(pins) == 1:
                continue

            common_pin_name = pins[0].name
            visible_pin = None
            common_etype = pins[0].etype
            min_pin_number = self.get_smallest_pin_number(pins)

            for pin in pins:
                if pin.number_int == None and not pos in self.non_numeric:
                    self.warning("Found non-numeric pin in a pinstack: {0}".format(pinString(pin)))
                    self.non_numeric.append(pos)

                # Check1: If a single pin in a stack is of type NC, we consider this an error
                if pin.etype == 'unconnected':
                    self.error("NC {pin} is stacked on other pins".format(
                               pin=pinString(pin),
                               x=pin.posx,
                               y=pin.posy))
                    self.NC_stacked.append(pin)

                # Check2: all pins should have the same name
                if pin.name != common_pin_name and not pos in self.different_names:
                    self.error("Pin names in the stack have different names")
                    self.different_names.append(pos)
                    for pin in pins:
                        self.errorExtra(pinString(pin))

                # Check3: exactly one pin should be visible
                if pin.is_hidden == False:
                    if visible_pin != None:
                        if self.more_then_one_visible == False:
                            self.error("A pin stack must have exactly one (1) visible pin")
                            for pin in pins:
                                self.errorExtra("{pin} is visible".format(pin=pinString(pin)))
                        self.more_then_one_visible = True
                    else:
                        visible_pin = pin

                    # the visible pin should have the lowest pin_number
                    if pin.number_int != None and pin.number_int != min_pin_number and not pos in self.visible_pin_not_lowest:
                        self.warning("The pin with the lowest number in a pinstack should be visible")
                        self.warningExtra("Pin {0} is visible, the lowest number in this stack is {1}".format(pinString(pin), min_pin_number))
                        self.visible_pin_not_lowest.append(pos)

                # Check4: all pins should have the same electrical type.
                #         exceptions are power-pin-stacks
                if pin.etype != common_etype:
                    # this could be one of the special cases
                    # at least one of the two checked pins need to be 'special' type. if not, this is an error
                    if pin.etype in self.special_power_pins or common_etype in self.special_power_pins:
                        possible_power_pin_stacks.append(pos)
                    else:
                        if not pos in self.different_types:
                            self.error("Pin names in the stack have different electrical types")
                            for pin in pins:
                                self.errorExtra("{0} is of type {1}".format(pinString(pin), pin.etype))
                            self.different_types.append(pos)

        # check the possible power pin_stacks
        special_stack_err = False
        for pos in possible_power_pin_stacks:
            pins = self.component.get_pinstacks()[pos]
            min_pin_number = self.get_smallest_pin_number(pins)

            # 1. consists only of output and passive pins
            # 2. consists only of power-output and passive pins
            # 3. consists only of power-input and passive pins
            # 4. consists only of power-output/output pins

            # count types of pins
            n_power_in  = self.count_pin_etypes(pins, 'power_in')
            n_power_out = self.count_pin_etypes(pins, 'power_out')
            n_output    = self.count_pin_etypes(pins, 'output')
            n_passive   = self.count_pin_etypes(pins, 'passive')
            n_others    = len(pins) - n_power_in - n_power_out - n_passive - n_output
            n_total     = len(pins)

            # check for cases 1..3
            if n_passive == n_total - 1 and (n_power_in == 1 or n_power_out == 1 or n_output == 1):
                # find the passive pins, they must be invisible
                for pin in pins:
                    if pin.etype == 'passive' and pin.is_hidden == False:
                        self.error("Passive pins in a pinstack are hidden")
                        special_stack_err = True
                        for ipin in pins:
                            if ipin.etype == 'passive' and ipin.is_hidden == False:
                                self.errorExtra("{0} is of type {1} and visible".format(pinString(ipin), ipin.etype))
                        break

                # find the non-passive pin, it must be visible. Also, it should have the lowest pin-number of all
                for pin in pins:
                    if pin.etype != 'passive':
                        # we found the non-passive pin
                        if pin.is_hidden == True:
                            self.error("Non passive pins in a pinstack are visible")
                            special_stack_err = True
                            self.errorExtra("{0} is of type {1} and invisible".format(pinString(pin), pin.etype))

                        if pin.number_int != None and pin.number_int != min_pin_number and not pos in self.visible_pin_not_lowest:
                            self.warning("The pin with the lowest number in a pinstack should be visible")
                            self.warningExtra("Pin {0} is visible, the lowest number in this stack is {1}".format(pinString(pin), min_pin_number))
                            self.visible_pin_not_lowest.append(pos)
                        break

            # check for case 4
            elif n_output == n_total or n_power_out == n_total:
                visible_pin = None
                # all but one pins should be invisible
                for pin in pins:
                    if pin.is_hidden == False:
                        if visible_pin == None:
                            # this is the first time we found a visible pin in this stack
                            visible_pin = pin
                            if pin.number_int != None and pin.number_int != min_pin_number and not pos in self.visible_pin_not_lowest:
                                self.warning("The pin with the lowest number in a pinstack should be visible")
                                self.warningExtra("Pin {0} is visible, the lowest number in this stack is {1}".format(pinString(pin), min_pin_number))
                                self.visible_pin_not_lowest.append(pos)
                        else:
                            # more than one visible pin found
                            special_stack_err = True
                            self.error("Only one pin in a pinstack is visible")
                            for vpin in list(filter(lambda p: p.is_hidden == False, pins)):
                                self.errorExtra("Pin {0} is visible".format(pinString(ivpin)))

            else:
                # pinstack is none of the above cases.
                self.error("Illegal pin stack configuration next to {}".format(pinString(pins[0])))
                self.errorExtra("Power input pins: {}".format(n_power_in))
                self.errorExtra("Power output pins: {}".format(n_power_out))
                self.errorExtra("Output pins: {}".format(n_output))
                self.errorExtra("Passive pins: {}".format(n_passive))
                self.errorExtra("Other type pins: {}".format(n_others))
                special_stack_err = True

        return self.more_then_one_visible or len(self.different_types) > 0 or len(self.NC_stacked) > 0 or len(self.different_names) > 0 or special_stack_err

    def fix(self):
        self.info("FIX not supported (yet)! Please fix manually.")
