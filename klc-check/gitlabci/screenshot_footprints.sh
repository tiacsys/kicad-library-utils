#!/usr/bin/env bash
set -e

source $(dirname ${BASH_SOURCE[0]})/common.sh

LAYERS="F.Cu,B.Cu,F.SilkS,B.SilkS,F.Fab,B.Fab,F.CrtYd,B.CrtYd,F.Adhes,B.Adhes"
CHANGES=$(git diff-tree --diff-filter=AMR --no-commit-id --name-only -r "$BASE_SHA" "$TARGET_SHA")
mkdir -p "$CI_BUILDS_DIR/tmp"
mkdir -p screenshots

for change in $CHANGES; do
    if [[ $change =~ .*\.kicad_mod ]]; then
        echo "Creating a board with footprint: $change"
        python3 "$CI_BUILDS_DIR/kicad-library-utils/scripts/create_board.py" "/$CI_PROJECT_DIR/$change" \
            "$CI_BUILDS_DIR/tmp/board.kicad_pcb"
        echo "Exporting svg"
        kicad-cli-nightly pcb export svg --page-size-mode 2 -l "$LAYERS" \
            -o "screenshots/$change.svg" "$CI_BUILDS_DIR/tmp/board.kicad_pcb"
        echo
        echo "Converting to png"
        mkdir -p screenshots/$(dirname "$change")
        inkscape -w 800 -b "#001023" "screenshots/$change.svg" -o "screenshots/$change.png"
    fi
done
