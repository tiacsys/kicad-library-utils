# -*- coding: utf-8 -*-

from rules.rule import *
import re

class Rule(KLCRule):
    """Only standard characters are used for naming libraries and components"""

    # Set of allowed chars. Some characters need to be escaped.
    allowed_chars = "a-zA-Z0-9_\-\.,\+"
    pattern = re.compile('^['+allowed_chars+']+$')
    forbidden = re.compile('([^'+allowed_chars+'])+')

    def check(self):
        name = str(self.module.name).lower()
        if not self.pattern.match(name):
            self.error("Footprint name must contain only legal characters")
            ilegal = re.findall(self.forbidden, name)
            self.errorExtra("Illegal character(s) '{c}' found".format(c="', '".join(ilegal)))
            return False
        return True

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        # Re-check line endings
        self.check()
