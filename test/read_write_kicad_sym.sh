#!/usr/bin/env bash

# This script file is used to compare to sexpr files
# with sexpr python file. Spaces and line positioning will be ignored

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 dirWithkicad_sym"
    exit 1
fi

function check {
  o1="$(mktemp)"
  python3 ../common/kicad_sym.py $1 > $o1

  # use git compare since it does a nice colorful output
  ../tools/compare_sexpr_files.sh $1 $o1
  R=$?

  # remove temp files, forward exit code
  rm $o1
  return $R;
} 


for file in $1/*.kicad_sym; do
  check $file
  R=$?
  if [ $R -ne 0 ]; then
    echo "Error on file $file"
    exit $R
  else
    echo "Passed $file"
  fi
done
