import re

from rules.rule import KLCRule


class Rule(KLCRule):
    """
    Create the methods check and fix to use with the kicad lib files.
    """

    def __init__(self, component):
        super(Rule, self).__init__(
            component, "Footprint filters should match all appropriate footprints"
        )

    def checkFilters(self, filters):

        self.bad_filters = []

        for fp_filter in filters:
            errors = []
            # Filter must contain a "*" wildcard
            if "*" not in fp_filter:
                errors.append("Does not contain wildcard ('*') character")

            else:
                if not fp_filter.endswith("*"):
                    errors.append("Does not end with ('*') character")

            if fp_filter.count(":") > 1:
                errors.append("Filter should not contain more than one (':') character")

            if errors:
                self.error(
                    "Footprint filter '{fp_filter}' not correctly formatted".format(
                        fp_filter=fp_filter
                    )
                )

                for error in errors:
                    self.errorExtra(error)

                self.bad_filters.append(fp_filter)

            # Extra warnings
            if (
                re.search(
                    r"(SOIC|SOIJ|SIP|DIP|SO|SOT-\d+"
                    r"|SOT\d+|QFN|DFN|QFP|SOP|TO-\d+"
                    r"|VSO|PGA|BGA|LLC|LGA)"
                    r"-\d+[W-_\*\?$]+",
                    fp_filter,
                    flags=re.IGNORECASE,
                )
                is not None
            ):
                self.warning(
                    "Footprint filter '{fp_filter}' seems to contain pin-number, but"
                    " should not!".format(fp_filter=fp_filter)
                )
            if ("-" in fp_filter) or ("_" in fp_filter):
                self.warning(
                    "Minuses and underscores in footprint filter '{fp_filter}' should be"
                    " escaped with '?' or '*'.".format(fp_filter=fp_filter)
                )

    def check(self):
        """
        Proceeds the checking of the rule.
        """

        filters = self.component.fplist

        if (
            not self.component.isGraphicSymbol() and not self.component.isPowerSymbol()
        ) and not filters:
            self.warning("No footprint filters defined")

        self.checkFilters(filters)

        return len(self.bad_filters) > 0

    def fix(self):
        """
        Proceeds the fixing of the rule, if possible.
        """
        self.info("FIX: not supported")
