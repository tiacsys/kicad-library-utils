# -*- coding: utf-8 -*-

from __future__ import division

from rules_footprint.rule import *

class Rule(KLCRule):
    """For surface-mount devices, placement type must be set to "Surface Mount" """

    def __init__(self, component, args):
        super().__init__(component, args)

        self.pth_count = 0
        self.smd_count = 0

    def check(self):
        """
        Proceeds the checking of the rule.
        The following variables will be accessible after checking:
            * pads_bounds
            * pads_distance
            * right_anchor
        """
        module = self.module

        self.pth_count = len(module.filterPads('thru_hole'))
        self.smd_count = len(module.filterPads('smd'))

        error = False

        if self.smd_count > 0 and module.attribute != 'smd':
            if module.attribute == 'virtual':
                self.warning("Footprint placement type set to 'virtual' - ensure this is correct!")
            # Only SMD pads?
            elif self.pth_count == 0:
                self.error("Surface Mount attribute not set")
                self.errorExtra("For SMD footprints, 'Placement type' must be set to 'Surface mount'")
                error = True
            else:
                self.warning("Surface Mount attribute not set")
                self.warningExtra("Both THT and SMD pads were found")
                self.warningExtra("Suggest setting 'Placement Type' to 'Surface Mount'")

        return error


    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        module = self.module
        if self.check():
            self.info("Set 'surface mount' attribute")
            module.attribute = 'smd'
