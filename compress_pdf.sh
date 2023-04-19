#!/bin/sh

COMPRESSION=prepress
# screen / ebook / printer /  prepress  / default

for file in "$@"; do
  filename="${file%.*}"
  ext="${file##*.}"
  echo "Compressing ${filename}.${ext} to ${filename}-small.${ext}"
  # Ghostscript does not like spaces in filenames, so we use temporary files to avoid any problems
  TMP_IN=$(mktemp)
  TMP_OUT=$(mktemp)
  cp "${filename}.${ext}" "${TMP_IN}"
  gs -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/"${COMPRESSION}" -sOutputFile="${TMP_OUT}" "${TMP_IN}"
  mv "${TMP_OUT}" "${filename}-compressed.${ext}"
  rm "${TMP_IN}"
done

