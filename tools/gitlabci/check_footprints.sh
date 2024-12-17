#!/bin/bash
source $(dirname ${BASH_SOURCE[0]})/common.sh

SCRIPT="$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_footprint.py"

echo "Comparing range $BASE_SHA to $TARGET_SHA"


mod_files=()

for change in $(git diff-tree --diff-filter=AMR --no-commit-id --name-only -r "$BASE_SHA" "$TARGET_SHA"); do
    if [[ $change =~ .*\.kicad_mod ]]; then
        mod_files+=("$CI_PROJECT_DIR/$change")
        echo "Checking: $change"
    fi
done

# Run the KLC checker on all the files
python3 "$SCRIPT" -vv \
    --junit junit.xml \
    --metrics \
    ${mod_files[@]}

KLC_ERRORS=$?

# check lib table
$CI_BUILDS_DIR/kicad-library-utils/klc-check/check_lib_table.py $CI_PROJECT_DIR/*.pretty \
    --table $CI_PROJECT_DIR/fp-lib-table \
    --junit junit.xml

TABLE_ERRORS=$?

# Table errors are always bad
if [ $TABLE_ERRORS -ne 0 ]; then
    exit 1
fi

if [ $KLC_ERRORS -eq 2 ]; then
    # Warnings
    exit 2
elif [ $KLC_ERRORS -eq 1 ]; then
    # Errors
    exit 1
fi

exit 0
