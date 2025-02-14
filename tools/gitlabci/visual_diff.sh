#!/usr/bin/env bash

set -e

# Root of the kicad-library-utils repo
klu_dir=$(realpath $(dirname ${BASH_SOURCE[0]})/../..)

base_commit="master"
target_commit="HEAD"
repo_dir=""
output_dir="diffs"
open_result=false


# usage: This function displays the usage information for the script.
# It provides a brief description of the script's purpose and the
# required/optional arguments that need to be passed to it.
# The function is typically called when the script is executed with
# incorrect or missing arguments, or when the user requests help.
usage() {
    echo "Usage: $0 [-r repo_dir] [-b base_sha] [-t target_sha] [-o output_dir]"
    echo "  -r repo_dir         Directory of the repository to compare"
    echo "  -b base_commit      Base commit SHA for the comparison (default: master)"
    echo "  -t target_commit    Target commit SHA for the comparison (default: HEAD)"
    echo "  -o output_dir       Directory to store the output diffs (default: diffs)"
    echo "  -O                  Open the result in a browser"
}

# Parse command line arguments
while getopts "r:b:t:o:O" opt; do
    case ${opt} in
        r )
            repo_dir=$OPTARG
            ;;
        b )
            base_sha=$OPTARG
            ;;
        t )
            target_sha=$OPTARG
            ;;
        o )
            output_dir=$OPTARG
            ;;
        O)
            open_result=true
            ;;
        \? )
            usage
            exit 1
            ;;
    esac
done

# Check if all required arguments are provided
if [ -z "$repo_dir" ] || [ -z "$base_sha" ] || [ -z "$target_sha" ] || [ -z "$output_dir" ]; then
    echo "Missing required arguments"
    usage
    exit 1
fi

echo "Comparing range $base_sha to $target_sha in '$repo_dir'"

cd "$repo_dir"
changed_objects=$(git diff-tree --diff-filter=AMR --no-commit-id --name-only "$base_sha" "$target_sha")

for change in $changed_objects; do
    if [[ $change =~ .*\.pretty || $change =~ .*\.kicad_sym ]]; then

        libname=$(realpath --relative-to="${repo_dir}" "${change}")
        # Strip extension and add .diff
        output_subdir="$output_dir/${libname%.*}.diff"
        echo "Diffing: $change to $output_subdir"
        python3 "$klu_dir/html-diff/src/html_diff.py" -j0 "$base_sha" "$change" -o "$output_subdir"
    fi
done

# If there is at least one *.diff, create the index.html
# The link path must be relative to ../ because index.html will be placed in the "index.html.diffs" directory
python3 "$klu_dir/html-diff/src/render_index_html.py" "$output_dir"

if [ "$open_result" = true ]; then
    xdg-open "$output_dir/index.html"
fi