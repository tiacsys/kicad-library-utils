#!/bin/bash
source $(dirname ${BASH_SOURCE[0]})/common.sh

SCRIPT="$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_footprint.py"

FP_ERROR_CNT=0

echo "Comparing range $BASE_SHA to $TARGET_SHA"
for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only -r "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.kicad_mod ]]; then
        echo "Checking: $change"
        python3 "$SCRIPT" "/$CI_PROJECT_DIR/$change" -vv --junit junit.xml
        FP_ERROR_CNT="$(($FP_ERROR_CNT + $?))"
    fi
done
echo "ErrorCount $FP_ERROR_CNT" > metrics.txt

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_lib_table.py $CI_PROJECT_DIR/*.pretty --table $CI_PROJECT_DIR/fp-lib-table
TAB_ERROR_CNT=$?
echo "LibTableErrorCount $TAB_ERROR_CNT" >> metrics.txt

exit $(($FP_ERROR_CNT + $TAB_ERROR_CNT))
