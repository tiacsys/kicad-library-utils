#!/usr/bin/env python3

import argparse
import os
import re
import sys
from glob import glob

common = os.path.abspath(os.path.join(sys.path[0], "..", "common"))

if common not in sys.path:
    sys.path.append(common)

from print_color import PrintColor
from rulebase import logError
from rules import get_all_symbol_rules
from rules.rule import KLCRule
from schlib import SchLib

parser = argparse.ArgumentParser(
    description=(
        "Checks KiCad library files (.lib) against KiCad Library Convention (KLC)"
        " rules. You can find the KLC at https://kicad.org/libraries/klc/"
    )
)
parser.add_argument("libfiles", nargs="+")
parser.add_argument(
    "-c",
    "--component",
    help="check only a specific component (implicitly verbose)",
    action="store",
)
parser.add_argument(
    "-p",
    "--pattern",
    help="Check multiple components by matching a regular expression",
    action="store",
)
parser.add_argument(
    "-r",
    "--rule",
    help=(
        "Select a particular rule (or rules) to check against (default = all rules)."
        ' Use comma separated values to select multiple rules. e.g. "-r 3.1,EC02"'
    ),
)
parser.add_argument(
    "-e",
    "--exclude",
    help=(
        "Exclude a particular rule (or rules) to check against. Use comma separated"
        ' values to select multiple rules. e.g. "-e 3.1,EC02"'
    ),
)
parser.add_argument("--fix", help="fix the violations if possible", action="store_true")
parser.add_argument(
    "--nocolor", help="does not use colors to show the output", action="store_true"
)
parser.add_argument(
    "-v",
    "--verbose",
    help=(
        "Enable verbose output. -v shows brief information, -vv shows complete"
        " information"
    ),
    action="count",
)
parser.add_argument(
    "-s",
    "--silent",
    help="skip output for symbols passing all checks",
    action="store_true",
)
parser.add_argument("-l", "--log", help="Path to JSON file to log error information")
parser.add_argument(
    "-w", "--nowarnings", help="Hide warnings (only show errors)", action="store_true"
)
parser.add_argument(
    "--footprints",
    help=(
        "Path to footprint libraries (.pretty dirs). Specify with e.g."
        ' "~/kicad/footprints/"'
    ),
)

args = parser.parse_args()

printer = PrintColor(use_color=not args.nocolor)

# Set verbosity globally
verbosity = 0
if args.verbose:
    verbosity = args.verbose

KLCRule.verbosity = verbosity

if args.rule:
    selected_rules = args.rule.split(",")
else:
    # ALL rules are used
    selected_rules = None

if args.exclude:
    excluded_rules = args.exclude.split(",")
else:
    excluded_rules = None

rules = []
for rule_name, rule in get_all_symbol_rules().items():
    if selected_rules is None or rule_name in selected_rules:
        if excluded_rules is None or rule_name not in excluded_rules:
            rules.append(rule.Rule)

# grab list of libfiles (even on windows!)
libfiles = []

if not rules:
    printer.red("No rules selected for check!")
    sys.exit(1)
else:
    if verbosity > 2:
        printer.regular("checking rules:")
        for rule in rules:
            printer.regular("  - " + str(rule))
        printer.regular("")

for libfile in args.libfiles:
    libfiles += glob(libfile)

if not libfiles:
    printer.red("File argument invalid: {f}".format(f=args.libfiles))
    sys.exit(1)

exit_code = 0

for libfile in libfiles:
    lib = SchLib(libfile)

    # Remove .lib from end of name
    lib_name = os.path.basename(libfile)[:-4]

    n_components = 0

    # Print library name
    if len(libfiles) > 1:
        printer.purple("Library: %s" % libfile)

    n_allviolations = 0

    for component in lib.components:

        # simple match
        match = True
        if args.component:
            match = match and args.component.lower() == component.name.lower()

        # regular expression match
        if args.pattern:
            match = match and re.search(
                args.pattern, component.name, flags=re.IGNORECASE
            )

        if not match:
            continue

        n_components += 1

        # check the rules
        n_violations = 0

        first = True

        for rule in rules:
            rule = rule(component)

            if args.footprints:
                rule.footprints_dir = args.footprints
            else:
                rule.footprints_dir = None

            if verbosity > 2:
                printer.white("Checking rule" + rule.name)

            rule.check()

            if args.nowarnings and not rule.hasErrors():
                continue

            if rule.hasOutput():
                if first:
                    printer.green("Checking symbol '{sym}':".format(sym=component.name))
                    first = False

                printer.yellow(
                    "Violating " + rule.name + " - " + rule.url, indentation=2
                )
                rule.processOutput(printer, verbosity, args.silent)

            # Specifically check for errors
            if rule.hasErrors():
                n_violations += rule.errorCount

                if args.log:
                    logError(args.log, rule.name, lib_name, component.name)

                if args.fix:
                    rule.fix()
                    rule.processOutput(printer, verbosity, args.silent)
                    rule.recheck()

        # No messages?
        if first:
            if not args.silent:
                printer.green(
                    "Checking symbol '{sym}' - No errors".format(sym=component.name)
                )

        # check the number of violations
        if n_violations > 0:
            exit_code += 1
        n_allviolations = n_allviolations + n_violations

    if args.fix and n_allviolations > 0:
        lib.save()
        printer.green(
            "saved '{file}' with fixes for {n_violations} violations.".format(
                file=libfile, n_violations=n_allviolations
            )
        )

sys.exit(exit_code)
