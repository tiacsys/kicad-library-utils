#!/usr/bin/env bash
set -e

source $(dirname ${BASH_SOURCE[0]})/common.sh

cd $CI_PROJECT_DIR

echo "Comparing range $BASE_SHA to $TARGET_SHA"
for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.pretty || $change =~ .*\.kicad_sym ]]; then
        echo "Diffing: $change"
        python3 "$CI_BUILDS_DIR/kicad-library-utils/html-diff/src/html_diff.py" "$BASE_SHA" "$change"
    fi
done
