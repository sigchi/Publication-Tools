#!/usr/bin/env python3

import webvtt
import sys

for f in sys.argv[1:]:
    try:
        print(f)
        w = webvtt.from_srt(f)
        w.save()
    except webvtt.errors.MalformedFileError:
        print("Malformed file, skipping!")

