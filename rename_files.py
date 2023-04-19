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
taps_to_pcs_id = {}

with open(CSV_FILE) as fd:
    dr = DictReader(fd)
    for paper in dr:
        pcs_to_taps_id[paper['PCS_ID']] = paper['PAPER ID']
        taps_to_pcs_id[paper['PAPER ID']] = paper['PCS_ID']

os.makedirs(dst_dir, exist_ok=True)

for f in glob.glob(f"{src_dir}/*.pdf"):
    pcs_id = re.match(r"^.*\/([a-z]+\d+)\.pdf", f)
    if pcs_id:
        pcs_id = pcs_id.group(1)
    taps_id = re.match(r"^.*\/(\d+)\.pdf", f)
    if taps_id:
        taps_id = taps_id.group(1)
    assert(not (taps_id and pcs_id))
    assert(taps_id or pcs_id)
    if taps_id:
        print("Moving:", taps_id, taps_to_pcs_id[taps_id])
        shutil.copy2(f, f"{dst_dir}/{taps_to_pcs_id[taps_id]}.pdf")
    elif pcs_id:
        print("Moving:", pcs_id, pcs_to_taps_id[pcs_id])
        shutil.copy2(f, f"{dst_dir}/{pcs_to_taps_id[pcs_id]}.pdf")


