# -*- coding: utf-8 -*-

from rules.rule import *


class Rule(KLCRule):
    """
    Create the methods check and fix to use with the kicad lib files.
    """
    v6 = True
    def __init__(self, component):
        super(Rule, self).__init__(component, 'Check part reference, name and footprint position and alignment')

    def check(self):
        """
        Proceeds the checking of the rule.
        The following variables will be accessible after checking:
            * recommended_ref_pos
            * recommended_ref_alignment
            * recommended_name_pos
            * recommended_name_alignment
            * recommended_fp_pos
            * recommended_fp_alignment
        """

        # check if component has just one rectangle, if not, skip checking
        ctr = self.component.get_center_rectangle(units=[0, 1])
        if not ctr:
            return False

        (maxx, top, minx, bottom) = ctr.get_boundingbox()

        # reference checking

        # if there is no pins in the top, the recommended position to ref is at top-center, horizontally centered
        if len(self.component.filter_pins(direction='D')) == 0:
            self.recommended_ref_pos = {'posx': 0, 'posy': (top + mil_to_mm(125))}
            self.recommended_ref_alignment = 'center'

        # otherwise, the recommended is put it before the first pin x position, right-aligned
        else:
            x = min([i.posx for i in self.component.filter_pins(direction='D')]) - mil_to_mm(100)
            self.recommended_ref_pos = {'posx': x, 'posy': (top + mil_to_mm(125))}
            self.recommended_ref_alignment = 'right'

        # get the current reference infos and compare them to recommended ones
        ref_need_fix = False
        ref = self.component.get_property("Reference")
        if ref:
            if (not ref.compare_pos(self.recommended_ref_pos['posx'], self.recommended_ref_pos['posy'])):
                self.warning("field: reference, {0}, recommended {1}".format(positionFormater(ref), positionFormater(self.recommended_ref_pos)))
                ref_need_fix = True
            if (ref.effects.h_justify != self.recommended_ref_alignment):
                self.warning("field: reference, justification {0}, recommended {1}".format(ref.effects.h_justify, self.recommended_ref_alignment))
                ref_need_fix = True
            # Does vertical alignment matter too?
            # What about orientation checking?

        # name checking

        # if there is no pins in the top, the recommended position to name is at top-center, horizontally centered
        if len(self.component.filter_pins(direction='D')) == 0:
            self.recommended_name_pos = {'posx': 0, 'posy': (top + mil_to_mm(50))}
            self.recommended_name_alignment = 'center'

        # otherwise, the recommended is put it before the first pin x position, right-aligned
        else:
            x = min([i.posx for i in self.component.filter_pins(direction='D')]) - mil_to_mm(100)
            self.recommended_name_pos = {'posx': x, 'posy': (top + mil_to_mm(50))}
            self.recommended_name_alignment = 'right'

        # get the current name infos and compare them to recommended ones
        name = self.component.get_property("Value")
        name_need_fix = False
        if name:
            if (not name.compare_pos(self.recommended_name_pos['posx'], self.recommended_name_pos['posy'])):
                self.warning("field: name, {0}, recommended {1}".format(positionFormater(name), positionFormater(self.recommended_name_pos)))
                name_need_fix = True
            if (name.effects.h_justify != self.recommended_name_alignment):
                self.warning("field: name, justification {0}, recommended {1}".format(name.effects.h_justify, self.recommended_name_alignment))
                name_need_fix = True


        # footprint checking

        # if there is no pins in the bottom, the recommended position to footprint is at bottom-center, horizontally centered
        if len(self.component.filter_pins(direction='U')) == 0:
            self.recommended_fp_pos = {'posx': 0, 'posy': (bottom - mil_to_mm(50))}
            self.recommended_fp_alignment = 'center'

        # otherwise, the recommended is put it after the last pin x position, left-aligned
        else:
            x = max([i.posx for i in self.component.filter_pins(direction='U')]) + mil_to_mm(50)
            self.recommended_fp_pos = {'posx': x, 'posy': (bottom - mil_to_mm(50))}
            self.recommended_fp_alignment = 'left'

        # get the current footprint infos and compare them to recommended ones
        fp_need_fix = False
        fp = self.component.get_property("Footprint")
        if fp:
            if (not fp.compare_pos(self.recommended_fp_pos['posx'], self.recommended_fp_pos['posy'])):
                self.warning("field: footprint, {0}, recommended {1}".format(positionFormater(fp), positionFormater(self.recommended_fp_pos)))
                fp_need_fix = True
            if (fp.effects.h_justify != self.recommended_fp_alignment):
                self.warning("field: footprint, justification {0}, recommended {1}".format(fp.effects.h_justify, self.recommended_fp_alignment))
                fp_need_fix = True
            fp_need_fix = True

        # This entire rule only generates a WARNING (won't fail a component, only display a message)
        return False

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        self.info("Fixing...")
        fp = self.component.get_property("Footprint")
        fp.posx = self.recommended_fp_pos['posx']
        fp.posy = self.recommended_fp_pos['posy']
        fp.effects.h_justify = self.recommended_fp_alignment

        ref = self.component.get_property("Reference")
        ref.posx = self.recommended_ref_pos['posx']
        ref.posy = self.recommended_ref_pos['posy']
        ref.effects.h_justify = self.recommended_ref_alignment

        val = self.component.get_property("Value")
        val.posx = self.recommended_name_pos['posx']
        val.posy = self.recommended_name_pos['posy']
        val.effects.h_justify = self.recommended_name_alignment

        self.recheck()
