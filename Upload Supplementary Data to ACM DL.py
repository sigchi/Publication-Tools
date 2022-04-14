#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script uploads videos and supplementary materials from the local filesystem
to the official ACM DL upload form.

It does not require any credentials.
Currently, the script does not check whether a file has already been uploaded.

"""

CSV_FILE = "./camera_ready.csv"
TAPS_CSV = "./taps_procs.csv" # contains the DOIs 
PROCEEDING_ID = "12338" # CHI '22 FP

VID_DIR = "./PCS_VID/"
SUP_DIR = "./PCS_SUP/"

# List URL is https://acmsubmit.acm.org/atyponListing.cfm?proceedingID=12338 etc.

##################################

print(INFO)


from base64 import b64encode
import requests
import re
import os
from csv import DictReader


TOKEN_URL = f"https://acmsubmit.acm.org/videosubmission.cfm?proceedingID={PROCEEDING_ID}"
UPLOAD_URL = "https://files.atypon.com/acm/"
SUBMIT_URL = "https://acmsubmit.acm.org/videosubmission2.cfm"

def b64(stringy):
    return b64encode(bytes(stringy, 'utf-8')).decode('utf-8')

# PCS does not have the DOIs - take them from TAPS
def get_doi_list(csvfile):
    doi = {}
    with open(csvfile) as fd:
        dr = DictReader(fd)
        for paper in dr:
            doi[paper['PCS_ID']] = paper['DOI'][16:] # remove URL prefix
    return doi

DOI = get_doi_list(TAPS_CSV)


def get_token():
    if DRY_RUN:
        return "TOKENTEST"
    r = requests.get(TOKEN_URL)
    token = re.search(r'data-token="([a-zA-Z0-9=]+)"', r.text).groups()[0]
    assert token
    print(f"Token: {token}")
    return token



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
    HEADERS = {'Authorization': f"Atypon {token}",
           'Tus-Resumable': '1.0.0',
           'Upload-Offset': '0',
           'Content-Type': 'application/offset+octet-stream',
           'Content-Length': filesize
          }
    r = requests.patch(UPLOAD_PATH, data=open(path,'rb'), headers=HEADERS)
    print("uploaded")
    assert(r.status_code==204)
    print(f"Uploaded to: {UPLOAD_PATH}")
    return UPLOAD_PATH



def commit_submission(author, email, doi, description, filename1, url1, filename2, url2):
    if DRY_RUN:
        print("DRY RUN: committing")
        return True
    post_metadata = {'yourName': author,
                 'yourEmailAddress': email,
                 'doi': doi,
                 'description': description,
                 'file-name-1': filename1,
                 'file-url-1': url1,
                 'file-name-2': filename2,
                 'file-url-2': url2,
                 'proceedingID': PROCEEDING_ID,
                 'ok2Go': 'YES'    
    }
    print(post_metadata)
    r = requests.post(SUBMIT_URL, data = post_metadata)  
    assert(r.status_code == 200)
    print(r)
    return True



def upload_submission(sub):
    if sub['Status'] == "complete":
        filename1, url1, filename2, url2 = '','','',''
        print(f"Uploading additional files for {sub['Paper ID']} ({sub['Title']})")
        doi = DOI[sub['Paper ID']] #map paper id to DOI
        doi_part = doi.split("/")[1]
        vid_file = doi_part+'.mp4'
        vid_path = VID_DIR+vid_file
        token = None
        if os.path.isfile(vid_path):
            if not token:
                token = get_token()
            print(f"    Uploading video file {vid_file}")
            description = f"Video for CHI '22 publication {sub['Paper ID']} ({doi})'"
            filename1 = vid_file
            url1 = upload_file(token, vid_path, vid_file, 'video/mp4', sub['Contact Name'], sub['Contact Email'], doi, description)
        
        zip_file = doi_part+'.zip'
        zip_path = SUP_DIR+zip_file
        if os.path.isfile(zip_path):
            if not token:
                token = get_token()
            print(f"    Uploading supplementary materials {zip_file}")
            description = f"Supplementary materials for CHI '22 publication {sub['Paper ID']} ({doi})'"
            filename2 = zip_file
            url2 = upload_file(token, zip_path, zip_file, 'application/zip', sub['Contact Name'], sub['Contact Email'], doi, description)
        
        if token: # indicates that we have uploaded something
            description = f"Supplementary materials for CHI '22 publication {sub['Paper ID']} ({doi})'"
            print("Committing")
            commit_submission(sub['Contact Name'], sub['Contact Email'], doi, description, filename1, url1, filename2, url2)           
    else:
        print(f"NOT READY {sub['Paper ID']} ({sub['Title']})")


fd = open(CSV_FILE, encoding='utf-8-sig')
submissions = DictReader(fd)
for submission in submissions:
    upload_submission(submission)

