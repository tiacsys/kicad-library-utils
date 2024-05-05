# extract the bash SHA hash from the gitlab API
# unfortunately it is not available via the environment variables
# if CI_JOB_TOKEN is set (else, expect the variables to be set externally)
if [ -v CI_JOB_TOKEN ]; then
  API_RESPONSE=$(curl -s -H "JOB_TOKEN: $CI_JOB_TOKEN" "https://gitlab.com/api/v4/projects/$CI_MERGE_REQUEST_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID")
  BASE_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['base_sha'])")
  TARGET_SHA=$( echo $API_RESPONSE | python3 -c "import sys, json; print (json.load(sys.stdin)['diff_refs']['head_sha'])")
fi


# unfortunately the URL where the assets are deployed differs depending on who runs the pipeline
# there are two cases, the CI can run in the project context, or in the contributors context
# we use the schema for a 'dynamic' URL from the manual
# https://docs.gitlab.com/ee/ci/environments/#set-a-dynamic-environment-url
if [ $CI_PROJECT_ROOT_NAMESPACE == "kicad" ]; then
  DYNAMIC_ENVIRONMENT_URL="https://$CI_PROJECT_ROOT_NAMESPACE.$CI_PAGES_DOMAIN/-/libraries/$CI_PROJECT_NAME/-/jobs/$CI_JOB_ID/artifacts/diffs/index.html.diff/index.html"
else
  DYNAMIC_ENVIRONMENT_URL="https://$CI_PROJECT_ROOT_NAMESPACE.$CI_PAGES_DOMAIN/-/$CI_PROJECT_NAME/-/jobs/$CI_JOB_ID/artifacts/diffs/index.html.diff/index.html"
fi
echo "DYNAMIC_ENVIRONMENT_URL=$DYNAMIC_ENVIRONMENT_URL" >> deploy.env
