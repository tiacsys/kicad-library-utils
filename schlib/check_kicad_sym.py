#!/usr/bin/env python3

import argparse
import traceback
import sys,os
from glob import glob # enable windows wildcards

common = os.path.abspath(os.path.join(sys.path[0], '..','common'))
if not common in sys.path:
    sys.path.append(common)
from kicad_sym import *

from print_color import *
from rules import __all__ as all_rules
from rules import *
from rules.rule import KLCRule
from rulebase import logError

def do_unittest(symbol, rules, metrics):
    error_count = 0
    m = re.match(r'(\w+)__(.+)__(.+)', symbol.name)
    unittest_result = m.group(1)
    unittest_rule = m.group(2)
    unittest_descrp = m.group(3)
    for rule in rules:
        rule = rule(symbol)
        if unittest_rule == rule.name and rule.v6 == True:
            rule.check()
            if unittest_result == 'Fail' and rule.errorCount == 0:
                printer.red("Test '{sym}' failed".format(sym=symbol.name))
                error_count += 1
                continue
            if unittest_result == 'Warn' and rule.warningCount() == 0:
                printer.red("Test '{sym}' failed".format(sym=symbol.name))
                error_count += 1
                continue
            if unittest_result == 'Pass' and (rule.warningCount() != 0 or rule.errorCount != 0):
                printer.red("Test '{sym}' failed".format(sym=symbol.name))
                error_count += 1
                continue
            printer.green("Test '{sym}' passed".format(sym=symbol.name))
                    
        else:
           continue
    return (error_count, warning_count)

def do_rulecheck(symbol, rules, metrics):
    symbol_error_count = 0
    symbol_warning_count = 0
    first = True
    for rule in rules:
        rule = rule(symbol)

        # check if this rule already is v6 compatible
        if rule.v6 == True:
          if verbosity > 2:
            printer.white("Checking rule " + rule.name)
          rule.check()
        else:
            continue


        if args.nowarnings and not rule.hasErrors():
            continue

        if rule.hasOutput():
            if first:
                printer.green("Checking symbol '{sym}':".format(sym=symbol.name))
                first = False

            printer.yellow("Violating " + rule.name, indentation=2)
            rule.processOutput(printer, args.verbose, args.silent)

        if rule.hasErrors():
            if args.log:
                logError(args.log, rule.name, lib_name, symbol.name)

        # increment the number of violations
        symbol_error_count += rule.errorCount
        symbol_warning_count += rule.warningCount()

    # No messages?
    if first:
        if not args.silent:
            printer.green("Checking symbol '{sym}' - No errors".format(sym=symbol.name))

    # done checking the symbol
    # count errors and update metrics
    metrics.append('{l}.{p}.warnings {n}'.format(l=symbol.libname, p=symbol.name, n=symbol_warning_count))
    metrics.append('{l}.{p}.errors {n}'.format(l=symbol.libname, p=symbol.name, n=symbol_error_count))
    return(symbol_error_count, symbol_warning_count)

def check_library(filename, rules, metrics, args):
    error_count  = 0
    warning_count = 0
    libname = ""
    if not os.path.exists(filename):
        printer.red('File does not exist: %s' % filename)
        return (1,0)

    if not filename.endswith('.kicad_sym'):
        printer.red('File is not a .kicad_sym : %s' % filename)
        return (1,0)

    try:
        library = KicadLibrary.from_file(filename)
    except Exception as e:
        printer.red('could not parse library: %s' % filename)
        if args.verbose:
            printer.red("Error: " + str(e))
            traceback.print_exc()
        return (1,0)

    for symbol in library.symbols:
        if args.component:
            if args.component.lower() != symbol.name.lower():
                continue

        if args.pattern:
            if not re.search(args.pattern, symbol.name, flags=re.IGNORECASE):
                continue

        # check which kind of tests we want to run
        if args.unittest:
            (ec, wc) = do_unittest(symbol, rules, metrics)
        else:
            (ec, wc) = do_rulecheck(symbol, rules, metrics)

        error_count += ec
        warning_count += wc
        libname = symbol.libname

    # done checking the lib
    metrics.append('{lib}.total_errors {n}'.format(lib=libname, n=error_count))
    metrics.append('{lib}.total_warnings {n}'.format(lib=libname, n=warning_count))
    return (error_count, warning_count)

parser = argparse.ArgumentParser(description='Checks KiCad library files (.kicad_sym) against KiCad Library Convention (KLC) rules. You can find the KLC at http://kicad-pcb.org/libraries/klc/')
parser.add_argument('kicad_sym_files', nargs='+')
parser.add_argument('-c', '--component', help='check only a specific component (implicitly verbose)', action='store')
parser.add_argument('-p', '--pattern', help='Check multiple components by matching a regular expression', action='store')
parser.add_argument('-r','--rule',help='Select a particular rule (or rules) to check against (default = all rules). Use comma separated values to select multiple rules. e.g. "-r 3.1,EC02"')
parser.add_argument('-e','--exclude',help='Exclude a particular rule (or rules) to check against. Use comma separated values to select multiple rules. e.g. "-e 3.1,EC02"')
#parser.add_argument('--fix', help='fix the violations if possible', action='store_true') # currently there is no write support for a kicad symbol
parser.add_argument('--nocolor', help='does not use colors to show the output', action='store_true')
parser.add_argument('-v', '--verbose', help='Enable verbose output. -v shows brief information, -vv shows complete information', action='count')
parser.add_argument('-s', '--silent', help='skip output for symbols passing all checks', action='store_true')
parser.add_argument('-l', '--log', help="Path to JSON file to log error information")
parser.add_argument('-w', '--nowarnings', help='Hide warnings (only show errors)', action='store_true')
parser.add_argument('-m', '--metrics', help='generate a metrics.txt file', action='store_true')
parser.add_argument('-u', '--unittest', help='unit test mode (to be used with test-symbols)', action='store_true')
parser.add_argument('--footprints', help='Path to footprint libraries (.pretty dirs). Specify with e.g. "~/kicad/footprints/"')

args = parser.parse_args()

printer = PrintColor(use_color=not args.nocolor)

# Set verbosity globally
verbosity = 0
if args.verbose:
    verbosity = args.verbose

KLCRule.verbosity = verbosity

exit_code = 0

if args.rule:
    selected_rules = args.rule.split(",")
else:
    selected_rules = None

rules = []

for r in all_rules:
    r_name = r.replace('_', '.')
    if selected_rules == None or r_name in selected_rules:
        rules.append(globals()[r].Rule)

files = []

for f in args.kicad_sym_files:
    files += glob(f)

if len(files) == 0:
    printer.red("File argument invalid: {f}".format(f=args.kicad_mod_files))
    sys.exit(1)


# now iterate over all files and check them
metrics = []
error_count = 0
warning_count = 0
for filename in files:
    (ec, wc) = check_library(filename, rules, metrics, args)
    error_count += ec
    warning_count += wc

# done checking all files
if args.metrics or args.unittest:
  metrics_file = file2 = open(r"metrics.txt","a+")
  for line in metrics:
    metrics_file.write(line + "\n")
  metrics_file.close()
sys.exit(0 if error_count == 0 else -1)




