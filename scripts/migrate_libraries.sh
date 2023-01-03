#!/bin/bash

# This script will migrate all libraries in current working directory to another directory
# it needs few environment variables defined:
#
# LIB_TYPE: fp or sym
# LIB_DEST: path to destination directory
# LIB_NAME_MASK: glob for find -name param to identify library files
#

echo "Migrating $LIB_TYPE libraries to version $(kicad-cli --version), destination: $LIB_DEST"

# Remove any matching libs
find "$LIB_DEST" -name "$LIB_NAME_MASK" -exec rm -rf "{}" \;

# Copy libs to destination
find . -name "$LIB_NAME_MASK" -exec cp -r "{}" "$LIB_DEST/{}" \;

LIBS=$(find $LIB_DEST -name "$LIB_NAME_MASK" -printf '%P\n')

for lib in $LIBS; do
    echo "Upgrading $lib"
    kicad-cli $LIB_TYPE upgrade --force "$LIB_DEST/$lib"
done
