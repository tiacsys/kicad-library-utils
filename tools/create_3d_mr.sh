#!/bin/bash

source $KICAD_LIBRARY_UTILS_DIR/tools/gitlabci/common.sh

export TMP_BUILD_DIR=`mktemp -d`
echo "Cloning 3d model repo"
git clone "${KICAD_MODELS_REPO}" "$TMP_BUILD_DIR/models" --branch master
cd src/generators
echo "/generate_changed_models.py -p ${BASE_SHA} -c ${TARGET_SHA} -o ${TMP_BUILD_DIR}/models -i -v"
`dirname $0`/generate_changed_models.py -p "${BASE_SHA}" -c "${TARGET_SHA}" -o "${TMP_BUILD_DIR}/models" -i -v
export branchname="gen-mr-${CI_MERGE_REQUEST_IID}"
cd "$TMP_BUILD_DIR/models"
git switch -c "$branchname"
git status
git config --global user.email "kicad-mr-bot@example.com"
git config --global user.name "KiCad MR bot"
git add \*.step
git commit --all --message "${CI_MERGE_REQUEST_TITLE}" --message "Output of merge request ${CI_MERGE_REQUEST_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID}"
git push -uf "https://gitlab-ci-token:${MR_3D_TOKEN}@gitlab.com/kicad/libraries/librarian-internal/kicad-packages3d-fork.git" "$branchname"
export MR_DESCRIPTION="Output of merge request ${CI_MERGE_REQUEST_PROJECT_URL}/-/merge_requests/${CI_MERGE_REQUEST_IID} ${CI_MERGE_REQUEST_TITLE}"
export MR_TITLE="Generator MR ${CI_MERGE_REQUEST_IID} ${CI_MERGE_REQUEST_TITLE}"
gitlab --private-token "${MR_3D_TOKEN}" project-merge-request create --project-id 68922623 --source-branch "$branchname" --target-branch master --allow-collaboration true --squash true --remove-source-branch true --target-project-id 21604637 --title "$MR_TITLE" --description "$MR_DESCRIPTION"
