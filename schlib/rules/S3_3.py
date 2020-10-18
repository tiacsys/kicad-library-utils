# -*- coding: utf-8 -*-

from rules.rule import *
import math


class Rule(KLCRule):
    v6 = True
    """
    Create the methods check and fix to use with the kicad lib files.
    """
    def __init__(self, component):
        super(Rule, self).__init__(component, 'Symbol outline and fill requirements')

    def check(self):
        """
        Proceeds the checking of the rule.
        The following variables will be accessible after checking:
            * center_rect_polyline
        """

        # no checks for power-symbols or graphical symbols:
        if self.component.is_power_symbol() or self.component.is_graphic_symbol():
            return False

        # check if component has just one rectangle, if not, skip checking
        center_rect_polyline = self.component.get_center_rectangle(range(self.component.unit_count))
        if center_rect_polyline == None:
            return False

        rectangle_need_fix = False
        if self.component.is_small_component_heuristics():
            if (not math.isclose(center_rect_polyline.stroke_width, self.mil_to_mm(10))):
                self.warning("Component outline is thickness {0}mil, recommended is {1}mil for standard symbol".format(self.mm_to_mil(center_rect_polyline.stroke_width), 10))
                self.warningExtra("exceptions are allowed for small symbols like resistor, transistor, ...")
                rectangle_need_fix = False
        else:
            if (not math.isclose(center_rect_polyline.stroke_width, self.mil_to_mm(10))):
                self.error("Component outline is thickness {0}mil, recommended is {1}mil".format(self.mm_to_mil(center_rect_polyline.stroke_width), 10))
                rectangle_need_fix = True

        if (center_rect_polyline.fill_type != 'background'):
            msg = "Component background is filled with {0} color, recommended is filling with {1} color".format(center_rect_polyline.fill_type, 'background')
            if self.component.is_small_component_heuristics():
                self.warning(msg)
                self.warningExtra("exceptions are allowed for small symbols like resistor, transistor, ...")
            else:
              self.error(msg)
              rectangle_need_fix = True

        return True if rectangle_need_fix else False

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        return False
