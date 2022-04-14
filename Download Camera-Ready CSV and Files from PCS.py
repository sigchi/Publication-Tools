#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script downloads a spreadsheet of camera-ready submissions from PCS.
Afterwards, it optionally downloads all final PDFs, videos and zip files with supplementary 
materials which are linked in the spreadsheet.
To do this, pass parameters `--all`, `--pdf`, `--video`, `--supplement` or a combination of these.
You need a file fields.csv that contains the metadata for each track

The downloaded spreadsheet is called `camera_ready.csv`.
Files are stored in folders ./PDF/, etc., as configured in fields.csv.
Files are named `{last part of DOI from CSV}-{file description}.{EXT}`, as configured in fields.csv
This is the format required by ACM for upload in the DL.

You can provide credentials for PCS in the environment variables PCS_USER / PCS_PASSWORD or enter them once prompted

"""

# stdlib
import re
import os
import sys
from csv import DictReader
from urllib.request import urlopen, urlretrieve, HTTPError
import getpass

# additional dependencies
import requests

# PCS_CONF_ID = "chi22b" # papers and notes

if sys.argv[-1].startswith("chi"):
    PCS_CONF_ID = "chi22b" # FP
else:
    print("Last parameter needs to be the conference track ID from PCS (starting with 'chi')")
    sys.exit()

##################################

print(INFO)
print(f"Downloading spreadsheet and files for: {PCS_CONF_ID}")



PCS_LOGIN_URL = "https://new.precisionconference.com/user/login"
PCS_USER = os.environ.get('PCS_USER') or input("PCS user: ")
PCS_PASSWORD = os.environ.get('PCS_PASSWORD') or getpass.getpass("PCS password: ")
PCS_SPREADSHEET_URL= f"https://new.precisionconference.com/{PCS_CONF_ID}/pubchair/csv/camera"


def get_camera_ready_csv():
    # get current data from PCS
    print("Downloading camera_ready.csv ... ")
    pcs_session = requests.Session()
    r = pcs_session.get(PCS_LOGIN_URL)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([a-z0-9#]+)"', r.text).groups()[0]
    r = pcs_session.post(PCS_LOGIN_URL, data={'username': PCS_USER, 'password': PCS_PASSWORD, 'csrf_token': csrf_token})
    r = pcs_session.get(PCS_SPREADSHEET_URL)
    with open("camera_ready.csv", "wb") as fd:
        fd.write(r.content)
    print("done.")

get_camera_ready_csv()


def get_filetypes(typefile):
    fd = open(typefile, "r")
    dr = DictReader(fd)
    filetypes = []
    for dic in dr:
        filetypes.append(dic)
    return filetypes

all_filetypes = get_filetypes("fields.csv")

# poor man's argparse
if "--all" in sys.argv:
    filetypes = all_filetypes
else:
    filetypes = []
    for ft in all_filetypes:
        if "--" + ft['dl_flag'] in sys.argv:
            filetypes.append(ft)

if len(filetypes) == 0:
    sys.exit()
        
for filetype in filetypes:
    try:
        os.makedirs(filetype['directory'])
    except FileExistsError:
        print(f"directory '{filetype['directory']}' already exists, writing into it")

fd = open("camera_ready.csv", encoding='utf-8-sig') # CSV has BOM
submissions = DictReader(fd)
for idx, submission in enumerate(submissions):
    print(f"[{idx}] Paper: {submission['Paper ID']} ({submission['Title']})")
    for filetype in filetypes:
        try:
            if len(submission[filetype['pcs_field']]) > 1:
                print(f"   Retrieving '{filetype['description']}'", end="")
                try:
                    doi = submission['DOI'].split("/")[-1]  # https://doi.org/10.1145/3491102.3501897 -> 3491102.3501897
                    filename = f"{filetype['directory']}/{doi}{filetype['suffix']}"
                    url = submission[filetype['pcs_field']]
                    doc = urlopen(url)
                    doc_size = int(doc.getheader("Content-Length"))
                    print(f"    > {doc_size/1000000.0:.2f} MB")
                    if os.path.exists(filename): # only download if file changed
                        file_size = os.stat(filename).st_size
                        if file_size == doc_size:
                            print("   >... already downloaded")
                            continue
                    # else
                    with open(filename, "wb") as fd:
                        fd.write(doc.read())
                except (ValueError, HTTPError):
                    print("   >... file not found on server")
            else:
                print(f"   >... '{filetype['description']}' not submitted")
        except KeyError:
            print(f"   >... field {filetype['pcs_field']} not in CSV")

fd.close()

