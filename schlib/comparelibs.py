#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This file compares two .lib files and generates a list of deleted / added / updated components.
This is to be used to compare an updated library file with a previous version to determine which components have been changed.
"""

import argparse
import sys
import os
from glob import glob
import fnmatch
import hashlib

# Path to common directory
common = os.path.abspath(os.path.join(sys.path[0], '..', 'common'))

if not common in sys.path:
    sys.path.append(common)

from kicad_sym import *
from print_color import *


def ExitError(msg):
    print(msg)
    sys.exit(-1)

parser = argparse.ArgumentParser( description= "Compare two .kicad_sym files to determine which symbols have changed")
parser.add_argument("--new", help="New (updated) .lib file(s), or folder of .kicad_sym files", nargs='+')
parser.add_argument("--old", help= "Old (original) .lib file(s), or folder of .kicad_sym files for comparison", nargs='+')
parser.add_argument("-v", "--verbose", help="Enable extra verbose output", action="store_true") 
parser.add_argument("--check", help="Perform KLC check on updated/added components", action='store_true')
parser.add_argument("--nocolor", help="Does not use colors to show the output", action='store_true')
parser.add_argument( "--design-breaking-changes", help= "Checks if there have been changes made that would break existing designs using a particular symbol.", action='store_true')
parser.add_argument("--check-aliases", help="Do not only check symbols but also aliases.", action='store_true')
parser.add_argument("--shownochanges", help="Show libraries that have not changed", action="store_true")

(args, extra) = parser.parse_known_args()

if not args.new:
    ExitError("New file(s) not supplied")
    # TODO print help

if not args.old:
    ExitError("Original file(s) not supplied")
    # TODO print help


def hash_file_sha256(fname):
    h = hashlib.sha256()
    with open(fname) as fh:
        for line in fh:
            h.update(line.encode('utf-8'))
    return (h.hexdigest())


def KLCCheck(lib, component):
    # Wrap library in "quotes" if required
    if " " in lib and '"' not in lib:
        lib = '"' + lib + '"'

    call = '{exe} {prefix}/check_kicad_sym.py {lib} -c={sym} -s -vv {nocolor}'.format(
        prefix=os.path.dirname(os.path.abspath(sys.argv[0])),
        exe=sys.executable,
        lib=lib,
        sym=component,
        nocolor="--nocolor " if args.nocolor else "")

    # Pass extra arguments to checklib script
    if len(extra) > 0:
        call += ' '.join([str(e) for e in extra])

    return os.system(call)


printer = PrintColor(use_color=not args.nocolor)

new_libs = {}
old_libs = {}

for lib in args.new:
    libs = glob(lib)

    for l in libs:
        if os.path.isdir(l):
            for root, dirnames, filenames in os.walk(l):
                for filename in fnmatch.filter(filenames, '*.kicad_sym'):
                    new_libs[os.path.basename(filename)] = os.path.abspath(
                        os.path.join(root, filename))

        elif l.endswith('.kicad_sym') and os.path.exists(l):
            new_libs[os.path.basename(l)] = os.path.abspath(l)

for lib in args.old:
    libs = glob(lib)

    for l in libs:
        if os.path.isdir(l):
            for root, dirnames, filenames in os.walk(l):
                for filename in fnmatch.filter(filenames, '*.kicad_sym'):
                    old_libs[os.path.basename(filename)] = os.path.abspath(
                        os.path.join(root, filename))

        elif l.endswith('.kicad_sym') and os.path.exists(l):
            old_libs[os.path.basename(l)] = os.path.abspath(l)

errors = 0
design_breaking_changes = 0

for lib_name in new_libs:

    lib_path = new_libs[lib_name]
    new_lib = KicadLibrary.from_file(lib_path)

    # New library has been created!
    if not lib_name in old_libs:
        if args.verbose:
            printer.light_green("Created library '{lib}'".format(lib=lib_name))

        # Check all the components!
        for sym in new_lib.symbols:
            if args.check:
                if not KLCCheck(lib_path, sym.name) == 0:
                    errors += 1
        continue

    # Library has been updated - check each component to see if it has been changed
    old_lib_path = old_libs[lib_name]
    old_lib = KicadLibrary.from_file(old_lib_path)

    # If library checksums match, we can skip entire library check
    if hash_file_sha256(old_lib_path) == hash_file_sha256(lib_path):
        if args.verbose and args.shownochanges:
            printer.yellow(
                "No changes to library '{lib}'".format(lib=lib_name))
        continue

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
        alias_info = ''
        if new_sym[symname].extends:
            alias_info = ' alias of {}'.format(sym.extends)

        if not symname in old_sym:
            if args.verbose:
                printer.light_green("New '{lib}:{name}'{alias_info}".format(
                    lib=lib_name, name=symname, alias_info=alias_info))

            if args.check:
                if not KLCCheck(lib_path, symname) == 0:
                    errors += 1

            continue

        if new_sym[symname].extends != old_sym[
                symname].extends and args.verbose:
            printer.white("Changed alias state of '{lib}:{name}'".format(
                lib=lib_name, name=symname))

        if not new_sym[symname].__eq__(old_sym[symname]):
            if args.verbose:
                printer.yellow("Changed '{lib}:{name}'{alias_info}".format(
                    lib=lib_name, name=symname, alias_info=alias_info))
            if args.design_breaking_changes:
                pins_moved = 0
                nc_pins_moved = 0
                pins_missing = 0
                nc_pins_missing = 0
                for pin_old in old_sym[sym].pins:
                    pin_new = new_sym[sym].get_pin_by_number(pin_old.num)
                    if pin_new is None:
                        if pin_old.etype == 'unconnected':
                            nc_pins_missing += 1
                        else:
                            pins_missing += 1
                        continue

                    if pin_old.posx != pin_new.posx or pin_old.posy != pin_new.posy:
                        if pin_old.etype == 'unconnected' and pin_new.etype == 'unconnected':
                            nc_pins_moved += 1
                        else:
                            pins_moved += 1

                if pins_moved > 0 or pins_missing > 0:
                    design_breaking_changes += 1
                    printer.light_purple(
                        "Pins have been moved, renumbered or removed in symbol '{lib}:{name}'{alias_info}"
                        .format(lib=lib_name,
                                name=symname,
                                alias_info=alias_info))
                elif nc_pins_moved > 0 or nc_pins_missing > 0:
                    design_breaking_changes += 1
                    printer.purple(
                        "Normal pins ok but NC pins have been moved, renumbered or removed in symbol '{lib}:{name}'{alias_info}"
                        .format(lib=lib_name,
                                name=symname,
                                alias_info=alias_info))

            if args.check:
                if not KLCCheck(lib_path, symname) == 0:
                    errors += 1

    for symname in old_sym:
        # Component has been deleted from library
        if not symname in new_sym:
            alias_info = ''
            if old_sym[sym].extends:
                alias_info = ' was an alias of {}'.format(
                    old_sym[symname].extends)

            if args.verbose:
                printer.red("Removed '{lib}:{name}'{alias_info}".format(
                    lib=lib_name, name=symname, alias_info=alias_info))
            if args.design_breaking_changes:
                design_breaking_changes += 1

# Entire lib has been deleted?
for lib_name in old_libs:
    if not lib_name in new_libs:
        if args.verbose:
            printer.red("Removed library '{lib}'".format(lib=lib_name))
        if args.design_breaking_changes:
            design_breaking_changes += 1

# Return the number of errors found ( zero if --check is not set )
sys.exit(errors + design_breaking_changes)
