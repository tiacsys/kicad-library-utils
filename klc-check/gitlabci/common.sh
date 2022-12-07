# extract the bash SHA hash from the gitlab API
# unfortunately it is not available via the environment variables
API_RESPONSE=$(curl -s -H "JOB_TOKEN: $CI_JOB_TOKEN" "https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID")
BASE_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['base_sha'])")
TARGET_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['head_sha'])")
