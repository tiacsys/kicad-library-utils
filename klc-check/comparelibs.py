#!/usr/bin/env python3
"""
This file compares two .lib files and generates a list of deleted / added / updated components.
This is to be used to compare an updated library file with a previous version to determine which
components have been changed.
"""

import argparse
import filecmp
import fnmatch
import os
import sys
from glob import glob

# Path to common directory
common = os.path.abspath(os.path.join(sys.path[0], "..", "common"))

if common not in sys.path:
    sys.path.append(common)

import check_symbol
from kicad_sym import KicadLibrary
from print_color import PrintColor
from rulebase import Verbosity


def ExitError(msg):
    print(msg)
    sys.exit(-1)


parser = argparse.ArgumentParser(
    description="Compare two .kicad_sym files to determine which symbols have changed"
)
parser.add_argument(
    "--new", help="New (updated) .lib file(s), or folder of .kicad_sym files", nargs="+"
)
parser.add_argument(
    "--old",
    help="Old (original) .lib file(s), or folder of .kicad_sym files for comparison",
    nargs="+",
)
parser.add_argument(
    "-v", "--verbose", help="Enable extra verbose output", action="store_true"
)
parser.add_argument(
    "--check", help="Perform KLC check on updated/added components", action="store_true"
)
parser.add_argument(
    "--nocolor", help="Does not use colors to show the output", action="store_true"
)
parser.add_argument(
    "--design-breaking-changes",
    help=(
        "Checks if there have been changes made that would break existing designs using"
        " a particular symbol."
    ),
    action="store_true",
)
parser.add_argument(
    "--check-aliases",
    help="Do not only check symbols but also aliases.",
    action="store_true",
)
parser.add_argument(
    "--shownochanges", help="Show libraries that have not changed", action="store_true"
)
parser.add_argument(
    "--exclude",
    help=(
        "Exclude a particular rule (or rules) to check against. Use comma separated"
        ' values to select multiple rules. e.g. "-e S3.1,EC02"'
    ),
)

(args, extra) = parser.parse_known_args()
printer = PrintColor(use_color=not args.nocolor)

if not args.new:
    ExitError("New file(s) not supplied")
    # TODO print help

if not args.old:
    ExitError("Original file(s) not supplied")
    # TODO print help


def build_library_dict(filelist):
    """
    Take a list of files, expand globs if required. Build a dict in for form {'libname': filename}
    """
    libs = {}
    for lib in filelist:
        flibs = glob(lib)

        for lib_path in flibs:
            if os.path.isdir(lib_path):
                for root, dirnames, filenames in os.walk(lib_path):
                    for filename in fnmatch.filter(filenames, "*.kicad_sym"):
                        libs[os.path.basename(filename)] = os.path.abspath(
                            os.path.join(root, filename)
                        )

            elif lib_path.endswith(".kicad_sym") and os.path.exists(lib_path):
                libs[os.path.basename(lib_path)] = os.path.abspath(lib_path)
    return libs


# prepare variables
new_libs = build_library_dict(args.new)
old_libs = build_library_dict(args.old)
errors = 0
design_breaking_changes = 0

# create a SymbolCheck instance
# add footprints dir if possible
if "footprints" in extra:
    fp = extra["footprints"]
else:
    fp = None
sym_check = check_symbol.SymbolCheck(
    None, args.exclude, Verbosity(2), fp, False if args.nocolor else True, silent=True
)

# iterate over all new libraries
for lib_name in new_libs:
    lib_path = new_libs[lib_name]
    new_lib = KicadLibrary.from_file(lib_path)

    # If library checksums match, we can skip entire library check
    if lib_name in old_libs:
        if filecmp.cmp(old_libs[lib_name], lib_path):
            if args.verbose and args.shownochanges:
                printer.yellow("No changes to library '{lib}'".format(lib=lib_name))
            continue

    # New library has been created!
    if lib_name not in old_libs:
        if args.verbose:
            printer.light_green("Created library '{lib}'".format(lib=lib_name))

        # Check all the components!
        for sym in new_lib.symbols:
            if args.check:
                (ec, wc) = sym_check.do_rulecheck(sym)
                if ec != 0:
                    errors += 1
        continue

    # Library has been updated - check each component to see if it has been changed
    old_lib_path = old_libs[lib_name]
    old_lib = KicadLibrary.from_file(old_lib_path)

    new_sym = {}
    old_sym = {}
    for sym in new_lib.symbols:
        if not args.check_aliases and sym.extends:
            continue
        new_sym[sym.name] = sym

    for sym in old_lib.symbols:
        if not args.check_aliases and sym.extends:
            continue
        old_sym[sym.name] = sym

    for symname in new_sym:
        # Component is 'new' (not in old library)
        alias_info = ""
        if new_sym[symname].extends:
            alias_info = " alias of {}".format(new_sym[symname].extends)

        if symname not in old_sym:
            if args.verbose:
                printer.light_green(
                    "New '{lib}:{name}'{alias_info}".format(
                        lib=lib_name, name=symname, alias_info=alias_info
                    )
                )

            if args.check:
                # only check new components
                (ec, wc) = sym_check.check_library(lib_path, component=symname)
                if ec != 0:
                    errors += 1

            continue

        if new_sym[symname].extends != old_sym[symname].extends and args.verbose:
            printer.white(
                "Changed alias state of '{lib}:{name}'".format(
                    lib=lib_name, name=symname
                )
            )

        if not new_sym[symname].__eq__(old_sym[symname]):
            if args.verbose:
                printer.yellow(
                    "Changed '{lib}:{name}'{alias_info}".format(
                        lib=lib_name, name=symname, alias_info=alias_info
                    )
                )
            if args.design_breaking_changes:
                pins_moved = 0
                nc_pins_moved = 0
                pins_missing = 0
                nc_pins_missing = 0
                for pin_old in old_sym[symname].pins:
                    pin_new = new_sym[symname].get_pin_by_number(pin_old.num)
                    if pin_new is None:
                        if pin_old.etype == "no_connect":
                            nc_pins_missing += 1
                        else:
                            pins_missing += 1
                        continue

                    if pin_old.posx != pin_new.posx or pin_old.posy != pin_new.posy:
                        if (
                            pin_old.etype == "no_connect"
                            and pin_new.etype == "no_connect"
                        ):
                            nc_pins_moved += 1
                        else:
                            pins_moved += 1

                if pins_moved > 0 or pins_missing > 0:
                    design_breaking_changes += 1
                    printer.light_purple(
                        "Pins have been moved, renumbered or removed in symbol"
                        " '{lib}:{name}'{alias_info}".format(
                            lib=lib_name, name=symname, alias_info=alias_info
                        )
                    )
                elif nc_pins_moved > 0 or nc_pins_missing > 0:
                    design_breaking_changes += 1
                    printer.purple(
                        "Normal pins ok but NC pins have been moved, renumbered or"
                        " removed in symbol '{lib}:{name}'{alias_info}".format(
                            lib=lib_name, name=symname, alias_info=alias_info
                        )
                    )

            if args.check:
                (ec, wc) = sym_check.do_rulecheck(new_sym[symname])
                if ec != 0:
                    errors += 1

    for symname in old_sym:
        # Component has been deleted from library
        if symname not in new_sym:
            alias_info = ""
            if old_sym[symname].extends:
                alias_info = " was an alias of {}".format(old_sym[symname].extends)

            if args.verbose:
                printer.red(
                    "Removed '{lib}:{name}'{alias_info}".format(
                        lib=lib_name, name=symname, alias_info=alias_info
                    )
                )
            if args.design_breaking_changes:
                design_breaking_changes += 1

# Check if an entire lib has been deleted?
for lib_name in old_libs:
    if lib_name not in new_libs:
        if args.verbose:
            printer.red("Removed library '{lib}'".format(lib=lib_name))
        if args.design_breaking_changes:
            design_breaking_changes += 1

# Return the number of errors found ( zero if --check is not set )
sys.exit(errors + design_breaking_changes)
