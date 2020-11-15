#!/bin/bash

SCRIPT="$CI_BUILDS_DIR/kicad-library-utils/pcb/check_kicad_mod.py"

# extract the bash SHA hash from the gitlab API
# unfortunately it is not available via the environment variables
API_RESPONSE=$(curl -s -H "JOB_TOKEN: $CI_JOB_TOKEN" "https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID")
BASE_SHA=$( echo $API_RESPONSE | python -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['base_sha'])")
TARGET_SHA=$( echo $API_RESPONSE | python -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['head_sha'])")

error_cnt=0

echo "Comparing range $BASE_SHA to $TARGET_SHA"
for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only -r "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.kicad_mod ]]; then
        echo "Checking: $change"
        python3 "$SCRIPT" "/$1/$change" -vv
        error_cnt="$(($error_cnt + $?))"
    fi
done
echo "ErrorCount $error_cnt" > metrics.txt
exit $error_cnt
