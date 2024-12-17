#!/bin/bash
# How to test locally:
# Inside the kicad-symbols folder, run
#     export BASE_SHA=$(git rev-parse master)
#     export TARGET_SHA=$(git rev-parse HEAD)
#     export CI_PROJECT_DIR=$(pwd)
#     export CI_BUILDS_DIR=..
#     ../kicad-library-utils/tools/gitlabci/check_symbols.sh

source $(dirname ${BASH_SOURCE[0]})/common.sh

# print python version
python3 -V

# Assert that $BASE_SHA and $TARGET_SHA are set
if [ -z "$CI_PROJECT_DIR" ]; then
  echo "CI_PROJECT_DIR is not set"
  exit 1
fi
if [ -z "$CI_BUILDS_DIR" ]; then
  echo "CI_BUILDS_DIR is not set"
  exit 1
fi
if [ -z "$BASE_SHA" ]; then
  echo "BASE_SHA is not set"
  exit 1
fi
if [ -z "$TARGET_SHA" ]; then
  echo "TARGET_SHA is not set"
  exit 1
fi

# clone required repos
git clone --depth 1 https://gitlab.com/kicad/libraries/kicad-footprints.git $CI_BUILDS_DIR/kicad-footprints

# get the list of files we want to compare
echo "Comparing range $BASE_SHA to $TARGET_SHA"
LIBS_NEW=$(git diff-tree --diff-filter=AMR --no-commit-id --oneline --name-only -r "$BASE_SHA" "$TARGET_SHA" | grep '\.kicad_sym$') #| sed -e "s#^#$CI_PROJECT_DIR/#;")
LIBS_OLD=$(git diff-tree --diff-filter=DMR --no-commit-id --oneline --name-only -r "$BASE_SHA" "$TARGET_SHA" | grep '\.kicad_sym$')

# do some debug output
echo "Found new Libraries: $LIBS_NEW"
echo "Found old Libraries: $LIBS_OLD"

# checkout the previous version of the 'old' files so we can compare against them
mkdir -p $CI_BUILDS_DIR/kicad-symbols-prev
for LIBNAME in $LIBS_OLD; do
  git cat-file blob "$BASE_SHA:$LIBNAME" > "$CI_BUILDS_DIR/kicad-symbols-prev/$LIBNAME"
done

# now run comparelibs
$CI_BUILDS_DIR/kicad-library-utils/klc-check/comparelibs.py -v \
  --old $CI_BUILDS_DIR/kicad-symbols-prev/* \
  --new $LIBS_NEW \
  --check --check-derived \
  --footprint_directory $CI_BUILDS_DIR/kicad-footprints \
  -m \
  --junit junit.xml
KLC_ERRORS=$?

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_lib_table.py $CI_PROJECT_DIR/*.kicad_sym \
    --table $CI_PROJECT_DIR/sym-lib-table \
    --junit junit.xml

TABLE_ERRORS=$?

# Table errors are always bad
if [ $TABLE_ERRORS -ne 0 ]; then
    exit 1
fi

if [ $KLC_ERRORS -eq 2 ]; then
    # Warnings
    exit 2
elif [ $KLC_ERRORS -ne 0 ]; then
    # Errors (or something else, assume bad)
    exit 1
fi

exit 0
