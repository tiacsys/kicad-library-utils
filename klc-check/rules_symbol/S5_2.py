import re
from typing import List

from kicad_sym import KicadSymbol
from rules_symbol.rule import KLCRule


class Rule(KLCRule):
    """Footprint filters should match all appropriate footprints"""

    def __init__(self, component: KicadSymbol):
        super().__init__(component)

        self.bad_filters: List[str] = []

    def checkFilters(self, filters: List[str]) -> None:

        self.bad_filters = []

        for filter in filters:
            errors = []
            # Filter must contain a "*" wildcard
            if '*' not in filter:
                errors.append("Does not contain wildcard ('*') character")

            else:
                if not filter.endswith('*'):
                    errors.append("Does not end with ('*') character")

            if filter.count(':') > 1:
                errors.append("Filter should not contain more than one (':') character")

            if len(errors) > 0:
                self.error("Footprint filter '{filter}' not correctly formatted".format(filter=filter))

                for error in errors:
                    self.errorExtra(error)

                self.bad_filters.append(filter)

            # Extra warnings
            if re.search('(SOIC|SOIJ|SIP|DIP|SO|SOT-\d+|SOT\d+|QFN|DFN|QFP|SOP|TO-\d+|VSO|PGA|BGA|LLC|LGA)-\d+[W-_\*\?$]+', filter, flags=re.IGNORECASE) is not None:
                self.warning("Footprint filter '{filter}' seems to contain pin-number, but should not!".format(filter=filter))
            if ('-' in filter) or ('_' in filter):
                self.warning("Minuses and underscores in footprint filter '{filter}' should be escaped with '?' or '*'.".format(filter=filter))

    def check(self) -> bool:
        """
        Proceeds the checking of the rule.
        """

        filters = self.component.get_fp_filters()

        if (not self.component.is_graphic_symbol() and not self.component.is_power_symbol()) and len(filters) == 0:
            self.warning("No footprint filters defined")

        self.checkFilters(filters)

        return len(self.bad_filters) > 0

    def fix(self) -> None:
        """
        Proceeds the fixing of the rule, if possible.
        """

        self.info("FIX: not supported")
