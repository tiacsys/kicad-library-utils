import os
import re

from rulebase import isValidName
from rules_footprint.rule import KLCRule


class Rule(KLCRule):
    """Footprint meta-data is filled in as appropriate"""

    def checkDocs(self) -> bool:
        description = self.module.description
        if not description:
            self.error("Description field is empty - add footprint description")
            # Cannot proceed now
            return True

        error = False
        if not re.search(r"https?://", description):
            self.error(
                "Description field does not contain a URL - add the URL to the datasheet"
            )
            error = True

        if re.match(r"https?://", description):
            self.error(
                "Description contains only a URL - add more description before the URL"
            )
            error = True

        return error

    def checkTags(self) -> bool:
        mod = self.module
        error = False
        if not mod.tags:
            self.error("Keyword field is empty - add keyword tags")
            return True

        illegal = [",", ";", ":"]
        mod.tags = str(mod.tags)
        # check for illegal tags
        if len(mod.tags) > 1:
            for char in illegal:
                if char in mod.tags:
                    self.error("Tags contain illegal character: ('{c}')".format(c=char))
                    error = True

        return error

    def _checkIllegalProperties(self) -> bool:
        error = False
        illegal_prop_names = ["footprint", "datasheet", "description"]

        for prop_name in illegal_prop_names:
            if prop_value := self.module.getPropertyValue(prop_name):
                self.error(
                    f"The '{prop_name}' field should not be set for a footprint: "
                    + f"(have '{prop_value}')"
                )
                error = True

        return error

    def check(self) -> bool:
        """
        Proceeds the checking of the rule.
        """

        err = False

        module = self.module
        if os.path.splitext(os.path.basename(module.filename))[0] != module.name:
            self.error(
                "footprint name (in file) was '{0}', but expected (from filename)"
                " '{1}'.\n".format(
                    module.name, os.path.splitext(os.path.basename(module.filename))[0]
                )
            )
            err = True

        if str(module.value["value"]) != module.name:
            self.error(
                "Value label '{lbl}' does not match filename '{fn}'".format(
                    lbl=module.value["value"], fn=module.name
                )
            )
            err = True

        if self.checkDocs():
            err = True

        if self.checkTags():
            err = True

        if self._checkIllegalProperties():
            err = True

        self.has_illegal_chars = False
        if not isValidName(module.name):
            self.error(
                "Module name '{name}' contains invalid characters as per KLC 1.7".format(
                    name=module.name
                )
            )
            err = True
            self.has_illegal_chars = True

        return err

    def fix(self) -> None:
        """
        Proceeds the fixing of the rule, if possible.
        """

        self.info("Setting footprint value to '{name}'".format(name=self.module.name))
        self.module.name = os.path.splitext(os.path.basename(self.module.filename))[0]
        self.module.value["value"] = self.module.name

        self.recheck()
