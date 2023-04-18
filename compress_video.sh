#!/bin/bash                                     
IFS=$'\n'
for file in "$@"; do
  filename="${file%.*}"
  ext="${file##*.}"
  ffmpeg -i "${file}" -vcodec libx264 -crf 28 "${filename}-small.${ext}" 
done
