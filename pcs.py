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
import time
import sys
from csv import DictReader
from urllib.request import urlopen, urlretrieve, HTTPError
import getpass

# additional dependencies
import requests
from tqdm import tqdm


if re.match(r"^[a-z]{2,}\d{2}[a-z]+$", sys.argv[-1]):
    PCS_CONF_ID = sys.argv[-1]
else:
    print("Last parameter needs to be the conference track ID from PCS (e.g. 'chi23b')")
    sys.exit()

##################################

print(INFO)
print(f"Downloading spreadsheet and files for: {PCS_CONF_ID}")

PCS_LOGIN_URL = "https://new.precisionconference.com/user/login"
PCS_USER = os.environ.get('PCS_USER') or input("PCS user: ")
PCS_PASSWORD = os.environ.get('PCS_PASSWORD') or getpass.getpass("PCS password: ")
PCS_TRACK_LIST = "https://new.precisionconference.com/get_table?table_id=user_chairing&conf_id=&type_id="
PCS_SPREADSHEET_URL = f"https://new.precisionconference.com/{PCS_CONF_ID}/pubchair/csv/camera"
LIST_FILE = f"./{PCS_CONF_ID}_submissions.csv"
FIELDS_FILE = f"./{PCS_CONF_ID}_fields.csv"


def file_is_current(file_path, max_seconds=300):
    file_mtime = os.path.getmtime(file_path)
    current_time = time.time()
    return (current_time - file_mtime) < max_seconds



def get_available_tracks():
    print("Getting list of tracks ... ")
    pcs_session = requests.Session()
    r = pcs_session.get(PCS_LOGIN_URL)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([a-z0-9#]+)"', r.text).groups()[0]
    r = pcs_session.post(PCS_LOGIN_URL, data={'username': PCS_USER, 'password': PCS_PASSWORD, 'csrf_token': csrf_token})
    r = pcs_session.get(PCS_TRACK_LIST)
    roles = r.json()['data']
    for role in roles:
        title = role[0]
        match = re.match(r'<a href="/(\w+)/(\w+)">(.+)</a>', role[3])
        track_id = match.group(1)
        role_id = match.group(2)
        track_name = match.group(3)
        print(f"{title} ({role_id}): {track_name} ({track_id})")


# you want to re-download the csv file every time because the download links for all media files
# are regenerated by PCS on download. If you use a 'stale' csv file, you will get 401 errors when 
# trying to download PDFs and other files.

def get_camera_ready_csv(overwrite=True):
    # get current data from PCS
    if overwrite is False and os.path.exists(LIST_FILE):
        print("file already exists - skipping download")
        return
    if os.path.exists(LIST_FILE) and file_is_current(LIST_FILE, 5 * 60):
        print("file already downloaded less than five minutes ago - skipping download")
        return
    print("Downloading camera_ready.csv ... ")
    pcs_session = requests.Session()
    r = pcs_session.get(PCS_LOGIN_URL)
    csrf_token = re.search(r'name="csrf_token" type="hidden" value="([a-z0-9#]+)"', r.text).groups()[0]
    r = pcs_session.post(PCS_LOGIN_URL, data={'username': PCS_USER, 'password': PCS_PASSWORD, 'csrf_token': csrf_token})
    r = pcs_session.get(PCS_SPREADSHEET_URL)
    with open(LIST_FILE, "wb") as fd:
        fd.write(r.content)
    print("done.")


def get_filetypes(typefile):
    fd = open(typefile, "r")
    dr = DictReader(fd)
    filetypes = []
    for dic in dr:
        filetypes.append(dic)
    return filetypes


def download_file(paper_id, url, filename, mode="only modified"):
    try:
        doc = None
        # avoid unnecessary downloads
        if mode == "only new":
            if os.path.exists(filename):  # only download if file changed
                tqdm.write("   >... already downloaded")
                return True
        elif mode == "only modified":
            doc = urlopen(url, timeout=10)
            doc_size = int(doc.getheader("Content-Length"))
            #print(f" ({doc_size/1000000.0:.2f} MB)")
            if os.path.exists(filename):  # only download if file changed
                file_size = os.stat(filename).st_size
                if file_size == doc_size:
                    tqdm.write("   >... already downloaded")
                    return True
        # ok, we want to download the file. make request if not already done
        if not doc:
            doc = urlopen(url, timeout=10)
            doc_size = int(doc.getheader("Content-Length"))
        with open(filename, 'wb') as fd:
            #print(f" ({doc_size/1000000.0:.2f} MB)")
            progress_bar = tqdm(total=doc_size, unit='iB', unit_scale=True, leave=False)
            while True:
                data = doc.read(1024*100)
                if not data:
                    break
                fd.write(data)
                progress_bar.update(len(data))
            progress_bar.close()
            return True
    except (ValueError, HTTPError) as e:
        tqdm.write("   >... file not found on server")
        print(e)
        return False


# mode: 
# "all" download files regardless of whether they already exist
# "only modified" get HTTP header for each file and only downloade existing files if local file size is different than server file size.
# "only new" only download files that do not already exist locally (this misses files that have been modified recently but is faster than checking file sizes

def download_files(start_index=0, mode="only modified"):
    all_filetypes = get_filetypes(FIELDS_FILE)

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
            os.makedirs(f"{PCS_CONF_ID}_{filetype['directory']}")
        except FileExistsError:
            print(f"directory '{PCS_CONF_ID}_{filetype['directory']}' already exists, writing into it")

    fd = open(LIST_FILE, encoding='utf-8-sig')  # CSV has BOM
    submissions = list(DictReader(fd))  # load in memory so that we get the line count
    for idx, submission in enumerate(tqdm(submissions, desc="Submissions processed", leave=False)):
        tqdm.write(f"[{idx}] Paper: {submission['Paper ID']} ({submission['Title']})")
        if idx < start_index:
            tqdm.write("    skipping")
            continue
        for filetype in filetypes:
            try:
                if len(submission[filetype['pcs_field']]) > 1:
                    tqdm.write(f"    Retrieving '{filetype['description']}'")
                    paper_id = submission['Paper ID']
                    filename = f"{PCS_CONF_ID}_{filetype['directory']}/{paper_id}{filetype['suffix']}"
                    url = submission[filetype['pcs_field']]
                    if download_file(paper_id, url, filename, mode):
                        pass 
                        #print("done")
                    else:
                        tqdm.write("failed")
                        return idx
                else:
                    tqdm.write(f"   >... '{filetype['description']}' not submitted")
            except KeyError:
                tqdm.write(f"   >... field {filetype['pcs_field']} not in CSV")
    fd.close()


def print_status():
    all_filetypes = get_filetypes(FIELDS_FILE)

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

    missing = {}
    for filetype in filetypes:
        missing[filetype['description']] = []

    fd = open(LIST_FILE, encoding='utf-8-sig')  # CSV has BOM
    submissions = DictReader(fd)
    for idx, submission in enumerate(submissions):
        print(f"[{idx}] Paper: {submission['Paper ID']} ({submission['Title']})")
        for filetype in filetypes:
            try:
                doi = submission['DOI'].split("/")[-1]  # https://doi.org/10.1145/3491102.3501897 -> 3491102.3501897
                paper_id = submission['Paper ID']
                if len(submission[filetype['pcs_field']]) < 1:
                    print(f"   >... '{filetype['description']}' not submitted")
                    missing[filetype['description']].append(paper_id)
            except KeyError:
                print(f"   >... field {filetype['pcs_field']} not in CSV")
    fd.close()
    for filetype in filetypes:
        print(filetype['description'])
        print(", ".join(missing[filetype['description']]))


def main():
    #print_status()
    #download_files(mode="only new")
    start_index = 0
    while True:  # reload camera-ready.csv on error
        get_camera_ready_csv()
        start_index = download_files(start_index, mode="only modified")
        if start_index is None:  #  finished
            break
        else:
            print(f"Restarting at submission #{start_index}")
    print("Done!")


if __name__ == "__main__":
    main()
