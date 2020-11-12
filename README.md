kicad-library-utils
===============

## klc-check directory

**test_schlib.sh**: A shell script used to validate the generation of files of the schlib module.

**check_kicad_mod.py**: Script for checking [KLC][] compliance of footprint files.

**kicad_mod.py**: A Python module for loading, editing, and saving KiCad footprint files.

**check_3d_coverage.py**: Script for checking which KiCad footprints in a `.pretty` library have 3D models. It also shows unused 3D model files.

[KLC]: http://kicad-pcb.org/libraries/klc/

## common directory

Contains various python librarys used by the check scrips and the generators.

## gitlabci directory

Contains helper scripts to run the CI for the following repos
* kicad-symbols
* kicad-footprints

How to use
==========

## Schematic Library Checker

    # first get into schlib directory
    cd kicad-library-utils/schlib

    # run the script passing the files to be checked
    ./check_kicad_sym.py path_to_lib1 path_to_lib2

    # to check a specific component you can use the -c flag
    ./check_kicad_sym.py -c component_name path_to_lib1

    # run the following 'h'elp command to see other options
    ./check_kicad_sym.py -h

## Footprint Checker

    # first get into pcb directory
    cd kicad-library-utils/pcb

    # run the script passing the files to be checked
    ./check_kicad_mod.py path_to_fp1.kicad_mod path_to_fp2.kicad_mod
    
    # Add `-v`, `-vv`, or `-vvv` for extra verbose output. The most useful is `-vv`, which explains in details the violations. Ex: 
    ./check_kicad_mod.py path_to_fp1.kicad_mod path_to_fp2.kicad_mod -vv

    # run the following 'h'elp command to see other options
    ./check_kicad_mod.py -h


## 3D Coverage Checker

    # first get into pcb directory
    cd kicad-library-utils/pcb

    # run the script to check all footprints
    ./check_3d_coverage.py

    # run the script to check only the specified .pretty folder
    ./check_3d_coverage.py --prettty Housings_SOIC

    # run the following 'h'elp command to see other options
    ./check_3d_coverage.py -h


Notice
======

The scripts use a different algorithm to generate files in relation to the KiCad saving action. That will result output files with more modified lines than expected, because the line generally are repositioned. However, the file still functional.

Always check the generated files by opening them on KiCad. Additionally, if you are working over a git repository (if not, you should) you can commit your work before proceed with the scripts, this will put you safe of any trouble. Also, you would use git diff to give a look at the modifications.
