#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script downloads a spreadsheet of camera-ready submissions from PCS.
Afterwards, it optionally downloads all final PDFs, videos and zip files with supplementary 
materials which are linked in the spreadsheet.
To do this, pass parameters `--all`, `--pdf`, `--video`, `--supplement` or a combination of these.

Adjust the spreadsheet URL to match your conference. 

The downloaded spreadsheet is called `camera_ready.csv`.
Files are stored in folders ./PCS_PDF/, ./PCS_VID/, and ./PCS_SUP/ .
Files are named `{Paper ID from CSV}.{EXT}`, e.g., `pn1234.mp4`

ATTENTION: existing files are overwritten.

"""

#PCS_CONF_ID = "chi22b" # FP
#PCS_CONF_ID = "chi22l" # LBR
#PCS_CONF_ID = "chi22e" # Student research competition
PCS_SPREADSHEET_URL= f"https://new.precisionconference.com/{PCS_CONF_ID}/pubchair/csv/camera"

##################################

print(INFO)
print(f"Downloading spreadsheet and files for: {PCS_CONF_ID}")


# stdlib
import re
import os
import sys
from csv import DictReader
from urllib.request import urlopen, urlretrieve, HTTPError
import getpass

# additional dependencies
import requests


PCS_LOGIN_URL = "https://new.precisionconference.com/user/login"
PCS_USER = os.environ.get('PCS_USER') or input("PCS user: ")
PCS_PASSWORD = os.environ.get('PCS_PASSWORD') or getpass.getpass("PCS password: ")


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

"""

FILES = [{'field': 'final_review_pdf', 'dir': 'PCS_PDF', 'ext': '.pdf'},
         {'field': 'Video Figure (Optional)', 'dir': 'PCS_VID', 'ext': '-video-figure.mp4'},
         {'field': 'Video Figure Captions (Required if the video figure contains spoken dialog)', 'dir': 'PCS_VID', 'ext': '-video-figure-captions.mp4'},
         {'field': 'video_preview', 'dir': 'PCS_PRV', 'ext': '-video-preview.mp4'},
         {'field': 'video_preview_captions', 'dir': 'PCS_SRT', 'ext': '-video-preview-caption.srt'},
         {'field': 'Supplemental Materials (Optional)', 'dir': 'PCS_SUP', 'ext': 'zip'},
         {'field': 'supplemental_materials', 'dir': 'PCS_SUP', 'ext': 'zip'},]
"""
filetypes = []

# poor man's argparse
if "--all" in sys.argv:
    filetypes = FILES
else:
    if "--pdf" in sys.argv:
        filetypes.append(FILES[0])
    if "--video" in sys.argv:
        filetypes.append(FILES[1])
    if "--preview" in sys.argv:
        filetypes.append(FILES[2])
        filetypes.append(FILES[3])
    if "--supplement" in sys.argv:
        filetypes.append(FILES[4])
        filetypes.append(FILES[5])
if len(filetypes) == 0:
    sys.exit()
        
for filetype in filetypes:
    try:
        os.makedirs(filetype['dir'])
    except FileExistsError:
        print(f"directory '{filetype['dir']}' already exists, writing into it")


fd = open("camera_ready.csv", encoding='utf-8-sig') # CSV has BOM
submissions = DictReader(fd)
for submission in submissions:
    print(f"Paper: {submission['Paper ID']} ({submission['Title']})")
    for filetype in filetypes:
        try:
            if len(submission[filetype['field']]) > 1:
                print(f"Retrieving {filetype['ext']} file: {submission[filetype['field']]}")
                try:
                    filename = f"{filetype['dir']}/{submission['Paper ID']}.{filetype['ext']}"
                    url = submission[filetype['field']]
                    doc = urlopen(url)
                    doc_size = int(doc.getheader("Content-Length"))
                    print(doc_size)
                    if os.path.exists(filename): # only download if file changed
                        file_size = os.stat(filename).st_size
                        if file_size == doc_size:
                            print("   >... already downloaded")
                            continue
                    # else
                    with open(filename, "wb") as fd:
                        fd.write(doc.read())
                    #urlretrieve(url, filename )
                except (ValueError, HTTPError):
                    print("   >... not found on server")
            else:
                print("   >... not submitted")
        except KeyError:
            print("   >... field not in CSV")

fd.close()

