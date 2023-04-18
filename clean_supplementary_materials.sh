#!/bin/bash

for f in *_SUP/*.zip
do
    zip -d $f "*/.DS_Store" "__MACOSX/*" "*/.git/*" "*/.gitignore"
done

