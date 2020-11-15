#!/usr/bin/env bash

# This script file is used to compare to sexpr files
# with sexpr python file. Spaces and line positioning will be ignored

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 fileA fileB"
    exit 1
fi


function normalize_sexpr {
# python code --- START
python3 << EOF
import sys
sys.path.append('../common')
import sexpr, re

# read file
f = open('$1')
data = ''.join(f.readlines())
out = sexpr.format_sexp(sexpr.build_sexp(sexpr.parse_sexp(data)))

# write file
f = open('$2', 'w')
f.write(out)
f.close()
EOF
# python code --- END
}

o1="$(mktemp)"
o2="$(mktemp)"
args=("$@")
normalize_sexpr ${args[0]} $o1
normalize_sexpr ${args[1]} $o2

# use git compare since it does a nice colorful output
git --no-pager diff --no-index --color-words $o1 $o2
R=$?

# remove temp files, forward exit code
rm $o1 $o2
exit $R
