#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script uploads videos and supplementary materials from the local filesystem
to the official ACM DL upload form.

It does not require any credentials.
Currently, the script does not check whether a file has already been uploaded.

"""

DRY_RUN = False

CSV_FILE = "./camera_ready.csv"
FIELDS_FILE = "./fields.csv"
#TAPS_CSV = "./taps_procs.csv" # contains the DOIs 
PROCEEDING_ID = "12337" # CHI '22 EA
#PROCEEDING_ID = "12338" # CHI '22 FP

# List URL is https://acmsubmit.acm.org/atyponListing.cfm?proceedingID=12338 etc.

##################################

print(INFO)


from base64 import b64encode
import requests
import re
import os
import sys
from csv import DictReader
import webvtt


TOKEN_URL = f"https://acmsubmit.acm.org/videosubmission.cfm?proceedingID={PROCEEDING_ID}"
UPLOAD_URL = "https://files.atypon.com/acm/"
SUBMIT_URL = "https://acmsubmit.acm.org/videosubmission2.cfm"

def b64(stringy):
    return b64encode(bytes(stringy, 'utf-8')).decode('utf-8')

# ensure that we only upload VTT files
def srt_to_vtt(filename):
    try:
        w = webvtt.read(filename) 
        print("file already in VTT format")
        return
    except (webvtt.errors.MalformedFileError, webvtt.errors.MalformedCaptionError):
        try: 
            w = webvtt.from_srt(filename)
            w.save(filename)
            print("SRT converted to VTT")
        except (webvtt.errors.MalformedFileError, webvtt.errors.MalformedCaptionError):
            print("Malformed file, skipping!")


def get_token():
    if DRY_RUN:
        return "TOKENTEST"
    r = requests.get(TOKEN_URL)
    token = re.search(r'data-token="([a-zA-Z0-9=]+)"', r.text).groups()[0]
    assert token
    print(f"Token: {token}")
    return token


def chunked(fd, chunksize=5*1024*1024):
    while data := fd.read(chunksize):
        yield data

def upload_file(token, path, filename, filetype, author, email, doi, description):
    if DRY_RUN: 
        print("DRY RUN: uploaded file")
        return ""
    filesize = str(os.path.getsize(path))
    metadata = f"filename {b64(filename)},filetype {b64(filetype)},yourName {b64(author)},yourEmailAddress {b64(email)},doi {b64(doi)},description {b64(description)}"
    HEADERS = {'Authorization': f"Atypon {token}",
           'Upload-Metadata': metadata, 
           'Upload-Length' : filesize,
           'Tus-Resumable': '1.0.0'        # required!
          }
    r = requests.post(UPLOAD_URL, headers=HEADERS)
    assert(r.status_code == 201)
    print("got upload path")
    UPLOAD_PATH = r.headers['Location']

    offset = 0
    for chunk in chunked(open(path, 'rb')):
        length = len(chunk)
        print(f"Uploaded {offset//(1000*1000)} / {filesize//(1000*1000)} MB", end='\r') 
        HEADERS = {'Authorization': f"Atypon {token}",
               'Tus-Resumable': '1.0.0',
               'Upload-Offset': str(offset),
               'Content-Type': 'application/offset+octet-stream',
               'Content-Length': str(length)
              }
        r = requests.patch(UPLOAD_PATH, data=chunk, headers=HEADERS)
        offset +=length
        #print(f"Headers: {r.headers}")
        #print(r.status_code)
        #print(r.text)
        assert(r.status_code==204)
    print(f"Uploaded to: {UPLOAD_PATH}")
    return UPLOAD_PATH



def commit_submission(author, email, doi, description, filenames_urls):
    if DRY_RUN:
        print("DRY RUN: committing")
        return True
    post_metadata = {'yourName': author,
                 'yourEmailAddress': email,
                 'doi': doi,
                 'description': description,
                 'proceedingID': PROCEEDING_ID,
                 'ok2Go': 'YES'    
    }
    for idx, fu in enumerate(filenames_urls):
        filename, url = fu
        post_metadata[f"file-name-{idx+1}"] = filename
        post_metadata[f"file-url-{idx+1}"] = url
    r = requests.post(SUBMIT_URL, data = post_metadata)  
    assert(r.status_code == 200)
    return True



def upload_submission(sub):
    if not sub['Status'] == "complete":
        print(f"NOT READY {sub['Paper ID']} ({sub['Title']})")
        return
    # else
    print(f"Uploading additional files for {sub['Paper ID']} ({sub['Title']})")
    doi = sub['DOI'].removeprefix("https://doi.org/")
    doi_part = doi.split("/")[-1]
    token = None  # TODO: do we need a new token for every submission?
    for filetype in FILETYPES:
        filename = f"{doi_part}{filetype['suffix']}"
        filepath = f"{filetype['directory']}/{filename}"
        if filepath.endswith(".vtt"):
            srt_to_vtt(filepath)
        if not os.path.isfile(filepath):
            print(f"File not found: {filepath}")
            continue
        if not token:
            token = get_token()
        print(f"Uploading {filetype['description']} file: {filepath}")
        description = f"{filetype['description']} for publication {sub['Paper ID']} ({doi_part})"
        url = upload_file(token, filepath, filename, filetype['mimetype'], sub['Contact Name'], sub['Contact Email'], doi, description)
        filenames_urls = [] # leftover from earlier version where all files for one submission were committed together. Left here in case the former behavior should be restored
        filenames_urls.append((filename, url))
        commit_description = f"{filetype['description']} for publication {sub['Paper ID']} ({doi_part})"
        print("Committing")
        commit_submission(sub['Contact Name'], sub['Contact Email'], doi, commit_description, filenames_urls)           
        print("Done")


all_filetypes = list(DictReader(open(FIELDS_FILE, "r")))
all_filetypes = [d for d in all_filetypes if d['upload_to_dl'] == "yes"]

# poor man's argparse
if "--all" in sys.argv:
    FILETYPES = all_filetypes
    # TODO: also check here whether dirs exist
else:
    FILETYPES = []
    for ft in all_filetypes:
        if "--" + ft['dl_flag'] in sys.argv:
            try:
                os.stat(ft['directory'])
                FILETYPES.append(ft)
            except FileNotFoundError:
                print(f"directory '{ft['directory']}' does not exist, skipping filetype")

if len(FILETYPES) == 0:
    sys.exit()


fd = open(CSV_FILE, encoding='utf-8-sig')
submissions = DictReader(fd)
for submission in submissions:
    upload_submission(submission)

