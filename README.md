kicad-library-utils
===============

## klc-check directory

**check_symbol.py**: Script for checking [KLC][] compliance of symbol files.

**check_footprint.py**: Script for checking [KLC][] compliance of footprint files.

**check_3d_coverage.py**: Script for checking which KiCad footprints in a `.pretty` library have 3D models. It also shows unused 3D model files.

**comparelibs.py**: Script to compare two versions of the same library. Used as part of the `kicad-symbols` CI.

[KLC]: http://kicad.org/libraries/klc/

### gitlabci directory

Contains helper scripts to run the CI for the following repos
* kicad-symbols
* kicad-footprints

## common directory

Contains various python libraries used by the check scripts and the generators.
* **kicad_mod.py**: A Python module for loading, editing, and saving KiCad footprint files.
* **kicad_sym.py**: A Python module for loading, editing, and saving KiCad symbol libraries.

## symbol-generators

**example-generator.py**: An example on how to create symbols using python

## tools directoy

**compare_sexpr_files.sh**: Normalizes and compares two sexpr files. Those can be `kicad_sym` or `kicad_mod` files.

## test directory

**read_write_kicad_sym.sh** Opens `.kicad_sym` files, parses them and writes them to a temp-file. Then the temp-file and original file are normalized and compared. If the reader and writer implementation are correct there should be no differences.

In the future it is planned to run this over the whole library to check if the scripts are working properly.

How to use
==========

## Symbol Library Checker

    # first get into klc-check directory
    cd kicad-library-utils/klc-check

    # run the script passing the files to be checked
    ./check_symbol.py path_to_lib1 path_to_lib2

    # to check a specific component you can use the -c flag
    ./check_symbol.py -c component_name path_to_lib1

    # run the following 'h'elp command to see other options
    ./check_symbol.py -h

## Footprint Checker

    # first get into klc-check directory
    cd kicad-library-utils/klc-check

    # run the script passing the files to be checked
    ./check_footprint.py path_to_fp1.kicad_mod path_to_fp2.kicad_mod

    # Add `-v`, `-vv`, or `-vvv` for extra verbose output. The most useful is `-vv`, which explains in details the violations. Ex: 
    ./check_footprint.py path_to_fp1.kicad_mod path_to_fp2.kicad_mod -vv

    # run the following 'h'elp command to see other options
    ./check_footprint.py -h


## 3D Coverage Checker

    # first get into klc-check directory
    cd kicad-library-utils/klc-check

    # run the script to check all footprints
    ./check_3d_coverage.py

    # run the script to check only the specified .pretty folder
    ./check_3d_coverage.py --pretty Package_SO

    # run the following 'h'elp command to see other options
    ./check_3d_coverage.py -h

## Compare Symbol Libraries

    # first get into klc-check directory
    cd kicad-library-utils/klc-check

    # run the script passing the libraries to be compared
    ./comparelibs.py --new path_to_new_lib --old path_to_old_lib

    # to also do a KLC check for each new or changed symbol use the --check flag
    ./comparelibs.py --new path_to_new_lib --old path_to_old_lib --check

    # run the following 'h'elp command to see other options
    ./comparelibs.py -h

## Check before commiting

Usually, you commit the footprint (or symbol) and let CI check your job.
You can let git pass the check before actually commiting. If it's red,
fix your footprint (or symbol) !

To automate the call, place a hook file in the footprint git's hooks directory,
**/somewhere/kicad/kicad-footprints/.git/hooks** named **pre-commit**
with containt:
```
#!/bin/bash

ERR=0
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)
for F in $STAGED_FILES; do
  if [[ "${F: -10}"  == ".kicad_mod" ]] ; then
    x=$(python3  /somewhere/kicad-library-utils/klc-check/check_footprint.py  -vv "$F")
    echo "$x"
    echo "$x" | grep -q "Violating" &&  ERR=1
  fi
done
exit $ERR
```
diff-filter=ACM stands for Added, Copied, Modified

The script skips non footprint-files. Use **git commit --no-verify** to bypass the hook.

Place the script in the footprint (or symbol) directory, not in the library-utils' git !


Notice
======

The scripts use a different algorithm to generate files in relation to the KiCad saving action. That will result output files with more modified lines than expected, because the line generally are repositioned. However, the file still functional.

Always check the generated files by opening them on KiCad. Additionally, if you are working over a git repository (if not, you should) you can commit your work before proceed with the scripts, this will put you safe of any trouble. Also, you would use git diff to give a look at the modifications.
