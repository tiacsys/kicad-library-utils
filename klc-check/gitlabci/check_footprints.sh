#!/bin/bash

SCRIPT="$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_footprint.py"

# extract the bash SHA hash from the gitlab API
# unfortunately it is not available via the environment variables
API_RESPONSE=$(curl -s -H "JOB_TOKEN: $CI_JOB_TOKEN" "https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID")
BASE_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['base_sha'])")
TARGET_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['head_sha'])")

FP_ERROR_CNT=0

echo "Comparing range $BASE_SHA to $TARGET_SHA"
for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only -r "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.kicad_mod ]]; then
        echo "Checking: $change"
        python3 "$SCRIPT" "/$CI_PROJECT_DIR/$change" -vv
        FP_ERROR_CNT="$(($FP_ERROR_CNT + $?))"
    fi
done
echo "ErrorCount $FP_ERROR_CNT" > metrics.txt

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_lib_table.py $CI_PROJECT_DIR/*.pretty --table $CI_PROJECT_DIR/fp-lib-table
TAB_ERROR_CNT=$?
echo "LibTableErrorCount $TAB_ERROR_CNT" >> metrics.txt

exit $(($FP_ERROR_CNT + $TAB_ERROR_CNT))
