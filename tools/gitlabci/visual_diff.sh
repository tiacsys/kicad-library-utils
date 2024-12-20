#!/usr/bin/env bash
set -e

source $(dirname ${BASH_SOURCE[0]})/common.sh

cd $CI_PROJECT_DIR

echo "Comparing range $BASE_SHA to $TARGET_SHA"
for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.pretty || $change =~ .*\.kicad_sym ]]; then
        echo "Diffing: $change"
        python3 "$CI_BUILDS_DIR/kicad-library-utils/html-diff/src/html_diff.py" -j0 "$BASE_SHA" "$change"
    fi
done

# If there is at least one *.diff, create the index.html
# The link path must be relative to ../ because index.html will be placed in the "index.html.diffs" directory
python3 "$CI_BUILDS_DIR/kicad-library-utils/html-diff/src/render_index_html.py" . -p "../"
# Move index.html to index.html.diff, so it will get moved by the (unmodified) gitlab-ci.yml
# to the [diffs] directory. We can't create this directory here, because then [mkdir diff]
# in .gitlab-ci.yml will fail
mkdir -p index.html.diff
mv index.html index.html.diff/index.html
