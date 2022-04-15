#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script uploads videos and supplementary materials from the local filesystem
to the official ACM DL upload form.

It does not require any credentials.
"""

DRY_RUN = False

#TAPS_CSV = "./taps_procs.csv" # contains the DOIs 
#PROCEEDING_ID = "12337" # CHI '22 EA
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
from lxml import etree


def b64(stringy):
    return b64encode(bytes(stringy, 'utf-8')).decode('utf-8')

# ensure that we only upload VTT files
def srt_to_vtt(filename):
    try:
        w = webvtt.read(filename) 
        print("    caption file already in VTT format")
        return
    except (webvtt.errors.MalformedFileError, webvtt.errors.MalformedCaptionError):
        try: 
            w = webvtt.from_srt(filename)
            w.save(filename)
            print("    caption file converted to VTT")
        except (webvtt.errors.MalformedFileError, webvtt.errors.MalformedCaptionError):
            print("    caption file, skipping conversion!")


def get_token():
    if DRY_RUN:
        return "TOKENTEST"
    r = requests.get(TOKEN_URL)
    token = re.search(r'data-token="([a-zA-Z0-9=]+)"', r.text).groups()[0]
    assert token
    #print(f"Token: {token}")
    return token


def chunked(fd, chunksize=5*1024*1024):
    while data := fd.read(chunksize):
        yield data

def upload_file(token, path, filename, filetype, author, email, doi, description):
    if DRY_RUN: 
        print("DRY RUN: uploaded file")
        return ""
    filesize = int(os.path.getsize(path))
    metadata = f"filename {b64(filename)},filetype {b64(filetype)},yourName {b64(author)},yourEmailAddress {b64(email)},doi {b64(doi)},description {b64(description)}"
    HEADERS = {'Authorization': f"Atypon {token}",
           'Upload-Metadata': metadata, 
           'Upload-Length' : str(filesize),
           'Tus-Resumable': '1.0.0'        # required!
          }
    r = requests.post(UPLOAD_URL, headers=HEADERS)
    assert(r.status_code == 201)
    print("got upload path")
    UPLOAD_PATH = r.headers['Location']

    offset = 0
    for chunk in chunked(open(path, 'rb')):
        length = len(chunk)
        print(f"    Uploaded {offset//(1000*1000)} / {filesize//(1000*1000)} MB", end='\r') 
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
    print(f"    Uploaded to: {UPLOAD_PATH}")
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
        if filetype['upload_to_dl'] == "no":
            print(f"Skipping '{filetype['description']}': not to be uploaded to DL")
            continue
        if filetype['upload_to_dl'] != "yes":  # explicit agreement needed!
            agreement_field = filetype['upload_to_dl']
            if sub[agreement_field] == "": # agreement missing
                print(f"Skipping '{filetype['description']}': no agreement from authors")
                continue
        # else
        filename = f"{doi_part}{filetype['suffix']}"
        filepath = f"{filetype['directory']}/{filename}"
        if filepath.endswith(".vtt"):
            srt_to_vtt(filepath)
        if not os.path.isfile(filepath):
            print(f"    No file for: {filepath} (probably not submitted)")
            continue
        if not token:
            token = get_token()
        description = f"{filetype['description']} for publication {sub['Paper ID']} ({doi_part})"
        if description in ALREADY_UPLOADED:
            print(f"    Already uploaded '{description}'... skipping it")
            continue
        # else
        print(f"    Uploading {filetype['description']} file: {filepath}")
        url = upload_file(token, filepath, filename, filetype['mimetype'], sub['Contact Name'], sub['Contact Email'], doi, description)
        filenames_urls = [] # leftover from earlier version where all files for one submission were committed together. Left here in case the former behavior should be restored
        filenames_urls.append((filename, url))
        commit_description = f"{filetype['description']} for publication {sub['Paper ID']} ({doi_part})"
        print("    Committing")
        commit_submission(sub['Contact Name'], sub['Contact Email'], doi, commit_description, filenames_urls)           
        print("    Done")


def get_uploaded_submissions(conf_id):
    URL=f"https://acmsubmit.acm.org/atyponListing.cfm?proceedingID={conf_id}"
    content = requests.get(URL).text
    root = etree.HTML(content)
    rows = root.xpath("//table[@id = 'publications']/tr")
    #print(f"Found {len(rows)} submissions (including excluded ones).")

    submissions = []
    for row in rows:
        submission= {}
        excluded = row[0][0].tail.endswith("excluded")
        submission['excluded'] = excluded
        submission['Paper Number'] = row[1].text
        submission['Load Date'] = row[2].text
        submission['Contact'] = row[3][0].text
        submission['Email'] = row[3][0].attrib['href'].removeprefix("mailto:")
        submission['DOI'] = row[4].text
        submission['File Descriptions'] = row[5].text
        submission['File URL'] = row[6][0].attrib['href']
        submissions.append(submission)

    already_uploaded = [d['File Descriptions'] for d in submissions]
    already_uploaded_without_excluded = [d['File Descriptions'] for d in submissions if not d['excluded']]
    excluded = [d['File Descriptions'] for d in submissions if d['excluded']]
    print(f"Found {len(already_uploaded)} already uploaded submissions (including {len(excluded)} excluded ones).")
    return already_uploaded



try:
    PROCEEDING_ID = int(sys.argv[-1])
except ValueError:
    PROCEEDING_ID = int(input("Conference ID (e.g. 12337): "))

CSV_FILE = "./camera_ready.csv"
FIELDS_FILE = "./fields.csv"
TOKEN_URL = f"https://acmsubmit.acm.org/videosubmission.cfm?proceedingID={PROCEEDING_ID}"
UPLOAD_URL = "https://files.atypon.com/acm/"
SUBMIT_URL = "https://acmsubmit.acm.org/videosubmission2.cfm"
ALREADY_UPLOADED = get_uploaded_submissions(PROCEEDING_ID)

all_filetypes = list(DictReader(open(FIELDS_FILE, "r")))
#all_filetypes = [d for d in all_filetypes if d['upload_to_dl'] == "yes"]

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
for idx, submission in enumerate(submissions):
    print(f"[{idx}] ", end="")
    upload_submission(submission)

