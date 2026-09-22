#!/bin/bash
# Summarize a directory: one line per file, '<name>: <lines> lines'.

dir=$1
for f in $dir/*; do
  lines=$(wc -l < $f)
  name=$(basename $f)
  echo "$name: $lines lines"
done
