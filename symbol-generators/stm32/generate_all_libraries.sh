#!/bin/sh

set -e

if [ $# -lt 1 ]; then
    echo "Error: $0 requires at least one argument: CUBEMX_MCU_DB_DIR"
fi

for family in $(python3 stm32_list_families.py $1 | grep -v L4+); do
    python3 stm32_generator.py $1 "MCU_ST_$family.kicad_sym" -p "$family*" --verify-datasheets --url-cache url_cache.sqlite3 --skip-without-footprint --skip-without-datasheet
done

wait

