#!/bin/bash

# print python version
python -V

# clone required repos
git clone --depth 1 https://gitlab.com/kicad/libraries/kicad-footprints.git $CI_BUILDS_DIR/kicad-footprints

# extract the bash SHA hash from the gitlab API
# unfortunately it is not available via the environment variables
API_RESPONSE=$(curl -s -H "JOB_TOKEN: $CI_JOB_TOKEN" "https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID")
BASE_SHA=$( echo $API_RESPONSE | python -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['base_sha'])")
TARGET_SHA=$( echo $API_RESPONSE | python -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['head_sha'])")

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
$CI_BUILDS_DIR/kicad-library-utils/schlib/comparelibs.py -v --old $CI_BUILDS_DIR/kicad-symbols-prev/* --new $LIBS_NEW --check --check-aliases --footprints $CI_BUILDS_DIR/kicad-footprints -m
SYM_ERROR_CNT=$?
echo "SymbolErrorCount $SYM_ERROR_CNT" >> metrics.txt

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/check_lib_table.py $CI_PROJECT_DIR/*.kicad_sym --table $CI_PROJECT_DIR/sym-lib-table
TAB_ERROR_CNT=$?
echo "LibTableErrorCount $TAB_ERROR_CNT" >> metrics.txt

exit $(($SYM_ERROR_CNT + $TAB_ERROR_CNT))
