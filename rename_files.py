#!/usr/bin/env python3

import sys
import os
import glob
import re
import shutil
from csv import DictReader

src_dir = sys.argv[1] 
dst_dir = sys.argv[2] 

CSV_FILE = "./taps_procs.csv"

pcs_to_taps_id = {}

with open(CSV_FILE) as fd:
    dr = DictReader(fd)
    for paper in dr:
        pcs_to_taps_id[paper['PCS_ID']] = paper['PAPER ID']

os.makedirs(dst_dir)

for f in glob.glob(f"{src_dir}/*.pdf"):
    pcs_id = re.match(r"^.*\/([a-z]+\d+)\.pdf", f).group(1)
    print("Moving:", pcs_id, pcs_to_taps_id[pcs_id])
    shutil.copy2(f, f"{dst_dir}/{pcs_to_taps_id[pcs_id]}.pdf")
