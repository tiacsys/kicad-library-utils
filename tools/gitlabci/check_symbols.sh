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

LIB_UPGRADE_ERROR_COUNT=$?

# Perform kicad-cli sym upgrade --force on each library
for LIBNAME in $LIBS_NEW; do
  echo "Upgrading $LIBNAME"

  # Perform sha256sum after
  sha256sum_before=$(sha256sum "$CI_PROJECT_DIR/$LIBNAME" | awk '{print $1}')
  kicad-cli sym upgrade "$CI_PROJECT_DIR/$LIBNAME" --force > /dev/null
  upgrade_status=$?
  sha256sum_after=$(sha256sum "$CI_PROJECT_DIR/$LIBNAME" | awk '{print $1}')

  if [ $upgrade_status -ne 0 ]; then
    echo "ERROR: 'kicad-cli sym upgrade --force $LIBNAME' failed (exit code $upgrade_status)."
    echo "This means the library can't be loaded in KiCad."
    echo "This might be caused by a derived symbol appearing before the base symbol in the file."
    # Fail only later so we can check all libraries
    LIB_UPGRADE_ERROR_COUNT=$(($LIB_UPGRADE_ERROR_COUNT + 1))
  elif [ "$sha256sum_before" != "$sha256sum_after" ]; then
    echo "ERROR: 'kicad-cli sym upgrade --force' changes $LIBNAME ."
    echo "Please re-save in KiCad or run 'kicad-cli sym upgrade --force $LIBNAME'"
    # Fail only later so we can check all libraries
    LIB_UPGRADE_ERROR_COUNT=$(($LIB_UPGRADE_ERROR_COUNT + 1))
  fi
done

# NOTE: We should not perform klc-check here since the library are broken or modified
# by the kicad-cli sym upgrade --force call.
if [ $LIB_UPGRADE_ERROR_COUNT -ne 0 ]; then
  echo "Fatal error: $LIB_UPGRADE_ERROR_COUNT libraries failed integrity check"
  exit $LIB_UPGRADE_ERROR_COUNT
fi

# checkout the previous version of the 'old' files so we can compare against them
mkdir -p $CI_BUILDS_DIR/kicad-symbols-prev
for LIBNAME in $LIBS_OLD; do
  git cat-file blob "$BASE_SHA:$LIBNAME" > "$CI_BUILDS_DIR/kicad-symbols-prev/$LIBNAME"
done

# now run comparelibs
$CI_BUILDS_DIR/kicad-library-utils/klc-check/comparelibs.py -v --old $CI_BUILDS_DIR/kicad-symbols-prev/* --new $LIBS_NEW --check --check-derived --footprint_directory $CI_BUILDS_DIR/kicad-footprints -m
SYM_ERROR_CNT=$?
echo "SymbolErrorCount $SYM_ERROR_CNT" >> metrics.txt

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_lib_table.py $CI_PROJECT_DIR/*.kicad_sym --table $CI_PROJECT_DIR/sym-lib-table
TAB_ERROR_CNT=$?
echo "LibTableErrorCount $TAB_ERROR_CNT" >> metrics.txt

exit $(($SYM_ERROR_CNT + $TAB_ERROR_CNT))
