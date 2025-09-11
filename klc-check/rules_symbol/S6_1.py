from rules_symbol.rule import KLCRule

RD_Map = [
    ("Y", ["Oscillator"]),
    ("U", ["CI_Test_S6.x"]),
]


class Rule(KLCRule):
    """If part is in oscillator library,"""

    def checkRD(self) -> bool:
        fail = False
        ref = self.component.get_property("Reference")
        if not ref:
            self.error("Component is missing Reference field")
            # can not do other checks, return
            return True

        for entry in RD_Map:
            if self.component.libname in entry[1]:
                if not ref.value.startswith(entry[0]):
                    self.error(
                        f"Library {self.component.libname} should have {entry[0]} as RD prefix"
                    )
                    fail = True

        return fail

    def check(self, exception=None) -> bool:

        return any([self.checkRD()])

    def fix(self) -> None:
        """
        Proceeds the fixing of the rule, if possible.
        """
        self.info("not supported")
        self.recheck()
