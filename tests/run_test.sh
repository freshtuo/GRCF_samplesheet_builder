#!/usr/bin/env sh

# exit immediately if any command exits with a non-zero status
set -e

sh tests/make_test_data.sh

samplesheet-tool -i tests/data/input_min.csv -o tests/out/resolved.csv \
  --i7-map tests/data/i7_illumina.csv:Index_ID:Index_Seq \
  --i5-map tests/data/i5_illumina.csv:Index_ID:Index_Seq \
  --pair-map tests/data/tenx_TT_setA.csv:Index_ID:Index_I7:Index_I5

