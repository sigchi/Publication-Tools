#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

CHUNK_SIZE = 5*1024*1024
#CHUNK_SIZE = 1*1024*1024
PACKET_SIZE = 1024*1024


# https://github.com/psf/requests/issues/2181
from http.client import HTTPConnection

HTTPConnection.__init__.__defaults__ = tuple(

    x if x != 8192 else PACKET_SIZE

    for x in HTTPConnection.__init__.__defaults__

)

from base64 import b64encode
import requests
import re
import os
import sys
from csv import DictReader
import webvtt
from lxml import etree

# additional dependencies
from tqdm import tqdm
print = tqdm.write

# Change to False once you have completed a test run
# While DRY_RUN = True, no actual uploads are made
DRY_RUN = False


INFO = """This script uploads videos and supplementary materials from the local filesystem
to the official ACM DL upload form.

It does not require any credentials.
"""


# no need to change these

UPLOAD_URL = "https://files.atypon.com/acm/"
SUBMIT_URL = "https://acmsubmit.acm.org/videosubmission2.cfm"
TAPS_CSV = "./taps_procs.csv" # contains the DOIs - used as fallback 
LIST_FILE_SUFFIX = "_camera_ready.csv"
FIELDS_FILE_SUFFIX = "_fields.csv"

def get_doi_list(csvfile):
    doi = {}
    with open(csvfile) as fd:
        dr = DictReader(fd)
        for paper in dr:
            doi[paper['PCS_ID']] = paper['DOI']            
    return doi

DOI_FALLBACK = get_doi_list(TAPS_CSV)


# if you leave these as 'None', contact author's details are used
# ACM staff prefers this to be the name of a proceedings chair so that they
# can be sure that the uploads are 'official'.
#UPLOADER_NAME = None
#UPLOADER_EMAIL = None
UPLOADER_NAME = "Raphael Wimmer (CHI '23 Proceedings Team)"
UPLOADER_EMAIL = "raphael.wimmer@ur.de"


# List URL is https://acmsubmit.acm.org/atyponListing.cfm?proceedingID=12338 etc.

##################################

# will be populated with parameters

PROCEEDING_ID = None


##################################


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
    TOKEN_URL = f"https://acmsubmit.acm.org/videosubmission.cfm?proceedingID={PROCEEDING_ID}"
    r = requests.get(TOKEN_URL)
    tokens = re.search(r'data-token="([a-zA-Z0-9=]+)"', r.text).groups()
    if tokens:
        token = tokens[0]
    else:
        raise RuntimeError("Token not available - is the portal currently ready for uploads?")
    assert token
    #print(f"Token: {token}")
    return token


# 5 MB seems to be the maximum chunk size the ACM portal accepts


def chunked(fd, chunk_size=CHUNK_SIZE):
    while data := fd.read(chunk_size):
        yield data


def upload_file(token, path, filename, upload_filename, filetype, author, email, doi, description):
    if DRY_RUN: 
        print(f"    DRY RUN: uploaded file {filename} as {upload_filename} ({description})")
        return ""
    filesize = int(os.path.getsize(path))
    metadata = f"filename {b64(upload_filename)},filetype {b64(filetype)},yourName {b64(author)},yourEmailAddress {b64(email)},doi {b64(doi)},description {b64(description)}"
    HEADERS = {'Authorization': f"Atypon {token}",
           'Upload-Metadata': metadata, 
           'Upload-Length' : str(filesize),
           'Tus-Resumable': '1.0.0'        # required!
          }
    r = requests.post(UPLOAD_URL, headers=HEADERS)
    assert(r.status_code == 201)
    print("got upload path")
    UPLOAD_PATH = r.headers['Location']

    progress_bar = tqdm(total=filesize, unit='iB', unit_scale=True, leave=False)
    offset = 0
    for chunk in chunked(open(path, 'rb')):
        length = len(chunk)
        #print(f"    Uploaded {offset//(1000*1000)} / {filesize//(1000*1000)} MB", end='\r') 
        HEADERS = {'Authorization': f"Atypon {token}",
               'Tus-Resumable': '1.0.0',
               'Upload-Offset': str(offset),
               'Content-Type': 'application/offset+octet-stream',
               'Content-Length': str(length)
              }
        r = requests.patch(UPLOAD_PATH, data=chunk, headers=HEADERS)
        progress_bar.update(length)
        offset +=length
        #print(f"Headers: {r.headers}")
        #print(r.status_code)
        #print(r.text)
        assert(r.status_code==204)
    print(f"    Uploaded to: {UPLOAD_PATH}")
    progress_bar.close()
    return UPLOAD_PATH



def commit_submission(author, email, doi, description, filenames_urls):
    if DRY_RUN:
        print(f"    DRY RUN: committing: {description}")
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



def upload_submission(track_id, sub, filetypes, already_uploaded_files):
    submission_ready_field = filetypes[0]['ready_field']
    if len(submission_ready_field) > 0:
        if sub[submission_ready_field] == "":
            print(f"NOT READY {sub['Paper ID']} ({sub['Title']})")
            return
    # else
    print(f"Uploading additional files for {sub['Paper ID']} ({sub['Title']})")
    doi = sub['DOI']
    if len(doi.strip()) == 0:
        doi = DOI_FALLBACK[sub['Paper ID']]
    assert(len(doi) > 0)
    doi = doi.removeprefix("https://doi.org/")
    doi_part = doi.split("/")[-1]
    assert(len(doi_part) > 0)
    token = None  # TODO: do we need a new token for every submission?
    for filetype in filetypes:
        if filetype['upload_to_dl'] == "no":
            print(f"Skipping '{filetype['description']}': not to be uploaded to DL")
            continue
        if filetype['upload_to_dl'] != "yes":  # explicit agreement needed!
            agreement_field = filetype['upload_to_dl']
            if sub[agreement_field] == "": # agreement missing
                print(f"Skipping '{filetype['description']}': no agreement from authors")
                continue
        # else
        filename = f"{sub['Paper ID']}{filetype['suffix']}"
        upload_filename = f"{doi_part}{filetype['suffix']}"
        filepath = f"{track_id}_{filetype['directory']}/{filename}"
        if not os.path.isfile(filepath):
            print(f"    No file for: {filepath} (probably not submitted)")
            continue
        if filepath.endswith(".vtt"):
            srt_to_vtt(filepath)
        if not token:
            token = get_token()
        #description = f"{filetype['description']} for Publication {sub['Paper ID']} (doi:{doi})"
        # Better - because this is what shows up on the DL page, so any DOI is irrelevant
        description = f"{filetype['description']}"
        if upload_filename in already_uploaded_files:
            print(f"    Already uploaded '{upload_filename}'... skipping it")
            continue
        # else
        if UPLOADER_NAME and UPLOADER_EMAIL:
            uploader_name, uploader_email = UPLOADER_NAME, UPLOADER_EMAIL
        else:
            uploader_name, uploader_email = sub['Contact Name'], sub['Contact Email'],
        print(f"    Uploading {filetype['description']} file: {filepath} as {upload_filename}")
        url = upload_file(token, filepath, filename, upload_filename, filetype['mimetype'], uploader_name, uploader_email,  doi, description)
        filenames_urls = [] # leftover from earlier version where all files for one submission were committed together. Left here in case the former behavior should be restored
        filenames_urls.append((upload_filename, url))
        commit_description = description  # the commit_description is what actually shows up on the ACM DL!
        print("    Committing")
        commit_submission(uploader_name, uploader_email, doi, commit_description, filenames_urls)           
        print("    Done")


def get_uploaded_submissions(conf_id, include_excluded=False):
    print("Getting already uploaded submissions")
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
        submission['Paper ID'] = row[1].text
        submission['Load Date'] = row[2].text
        submission['Contact'] = row[3][0].text
        submission['Email'] = row[3][0].attrib['href'].removeprefix("mailto:")
        submission['DOI'] = row[4].text
        submission['File Description'] = row[5].text
        submission['File Name'] = row[6][0].text
        submission['File URL'] = row[6][0].attrib['href']
        submissions.append(submission)

    already_uploaded = submissions
    already_uploaded_without_excluded = [d for d in submissions if not d['excluded']]
    excluded = [d for d in submissions if d['excluded']]
    print(f"Found {len(already_uploaded)} already uploaded submissions (including {len(excluded)} excluded ones).")
    if include_excluded:
        return already_uploaded
    else:
        return already_uploaded_without_excluded



def upload(track_id, filetypes):
    ALREADY_UPLOADED_FILES = [sub['File Name'] for sub in get_uploaded_submissions(PROCEEDING_ID)]
    fd = open(f"{track_id}{LIST_FILE_SUFFIX}", encoding='utf-8-sig')  # CSV has BOM
    submissions = DictReader(fd)
    for idx, submission in enumerate(tqdm(submissions, desc="Submissions processed", leave=False)):
        print(f"[{idx}] Paper: {submission['Paper ID']} ({submission['Title']})")
        upload_submission(track_id, submission, filetypes, ALREADY_UPLOADED_FILES)


def print_help():
    print("...")

def list_status():
    for sub in get_uploaded_submissions(PROCEEDING_ID):
        print(f"{sub['File Name']} - {sub['File Description']} for {sub['Paper ID']} ({sub['File URL']})")

def download():
    print("Not implemented yet")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
    else:
        PROCEEDING_ID = int(sys.argv[2])

        if sys.argv[1] == "list":
            list_status()
        elif sys.argv[1] == "download":
            download()
        elif sys.argv[1] == "upload":
            track_id = sys.argv[3]
            filetypes = sys.argv[4:]
            all_filetypes = list(DictReader(open(f"{track_id}{FIELDS_FILE_SUFFIX}", "r")))
            #all_filetypes = [d for d in all_filetypes if d['upload_to_dl'] == "yes"]
            # poor man's argparse
            if "all" in filetypes:
                filetypes = all_filetypes
            else:
                filetypes = []
                for ft in all_filetypes:
                    if ft['dl_flag'] in sys.argv:
                        try:
                            os.stat(f"{track_id}_{ft['directory']}")
                            filetypes.append(ft)
                        except FileNotFoundError:
                            print(f"directory '{track_id}_{ft['directory']}' does not exist, skipping filetype")
            if len(filetypes) == 0:
                sys.exit()
            upload(track_id, filetypes)
        else:
            print_help()
