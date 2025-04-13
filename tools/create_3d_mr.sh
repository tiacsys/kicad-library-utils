#!/bin/bash

if [ -z $1 ]; then
  TARGET_SHA="HEAD"
else
  TARGET_SHA=$1
fi

if [ -z $BASE_SHA ]; then
  BASE_SHA="$TARGET_SHA~1"
fi

export BUILDTARGET=`realpath "$CI_BUILDS_DIR"`
echo "Cloning 3d model repo"
git clone "${KICAD_MODELS_REPO}" "$BUILDTARGET/models" --branch master
cd 3d-model-generators
`dirname $0`/generate_changed_models.py -p "${BASE_SHA}" -c "${TARGET_SHA}" -o "${BUILDTARGET}/models" -i
export branchname="gen-mr-${CI_MERGE_REQUEST_IID}"
cd "$BUILDTARGET/models"
git switch -c "$branchname"
git status
git config --global user.email "kicad-mr-bot@example.com"
git config --global user.name "KiCad MR bot"
git add \*.step
git add \*.wrl
git commit --all --message "${CI_MERGE_REQUEST_TITLE}" --message "Output of merge request ${CI_MERGE_REQUEST_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID}"
echo git push -uf "https://gitlab-ci-token:${MR_3D_TOKEN}@gitlab.com/kicad/libraries/librarians/kicad-packages3d-fork.git" "$branchname"
export MR_DESCRIPTION="Output of merge request ${CI_MERGE_REQUEST_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID} ${CI_MERGE_REQUEST_TITLE}"
export MR_TITLE="Generator MR ${CI_MERGE_REQUEST_IID} ${CI_MERGE_REQUEST_TITLE}"
gitlab --private-token "${MR_3D_TOKEN}" project-merge-request create --project-id 68922623 --source-branch "$branchname" --target-branch master --allow-collaboration true --squash true --remove-source-branch true --target-project-id 21604637 --title "$MR_TITLE" --description "$MR_DESCRIPTION"
rm -rf $CI_BUILDS_DIR
