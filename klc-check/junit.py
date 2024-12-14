from xml.etree import ElementTree as ET
import os
import sys


# Path to common directory
common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, "common")
)

if common not in sys.path:
    sys.path.insert(0, common)

from rulebase import Severity

type ComponentName = str

SeverityToStr = {
    Severity.ERROR: "Errors",
    Severity.WARNING: "Warnings",
}


class JunitReport:
    """ A class to create a JUnit report from a dictionary of errors """

    def __init__(self):
        self.problems: dict[ComponentName, dict[Severity, list[str]]] = {}
        # problems is a dict that should look like so:
        # {
        #     "Component Name": {
        #         "ERR": ["Error Messages", ...],
        #         "WARN": ["Error Messages", ...],
        #     },
        #     "Component Name": {
        #     ...
        #     }
        # }

    def add_problem(self, component_name: str, severity: Severity, error_message: str):
        if component_name not in self.problems:
            self.problems[component_name] = {}
        if severity not in self.problems[component_name]:
            self.problems[component_name][severity] = []
        self.problems[component_name][severity].append(error_message)

    def create_report(self, xml_path: str):
        testsuites = ET.Element("testsuites")

        testsuite = ET.SubElement(testsuites, "testsuite", {
            "name": "Test Suite",
            "tests": "1",  # XXX TODO
            "failures": "1",  # XXX TODO
        })

        for component_name, problems_severity in self.problems.items():
            for severity, problems in problems_severity.items():
                # Create a test case for each component×severity
                testcase = ET.SubElement(testsuite, "testcase", {
                    "name": f"{component_name} - {SeverityToStr[severity]}",
                })

                # Each error/warning is a failure
                for problem in problems:
                    ET.SubElement(testcase, "failure", {
                        "message": str(problem),
                    }).text = str(problem)

        t = ET.ElementTree(testsuites)
        ET.indent(t)
        t.write(xml_path, encoding="utf-8", xml_declaration=True)
