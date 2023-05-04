#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script downloads a spreadsheet of submissions from TAPS.
Afterwards, it optionally downloads all final PDFs and HTML files (but no media linked in the HTML).
To do this, pass parameters `--all`, `--pdf`, `--html`, or a combination of these.

Adjust the TAPS ID to match your conference. 

The downloaded spreadsheet is called `taps_procs.csv`.
Files are stored in folders ./TAPS_PDF/ and ./TAPS_HTML/ .
Files are named `{Paper ID from PCS}_{Paper ID in TAPS}.{EXT}`, e.g., `pn1234_14.pdf`
This filename is used by linting tools to check PCS and TAPS metadata, so the filename needs to contain both fields.

ATTENTION: existing files are overwritten.
"""

##################################

print(INFO)

# stdlib
from lxml import etree
import re
import time
import os
import sys
from csv import DictWriter, DictReader
import getpass
from urllib.request import urlopen, urlretrieve, HTTPError

# additional
import requests

from tqdm import tqdm
print = tqdm.write


CONF_ID = os.environ.get('CONF_ID') or input("Conference ID: ")
SESSION_PAGE = 'https://camps.aptaracorp.com/ACMConference/'
LOGIN_PAGE = 'https://camps.aptaracorp.com/ACMConference/login.html'
METADATA_PAGE = 'https://camps.aptaracorp.com/ACMConference/showpaperdetails.html?proceeding_ID=' + CONF_ID + '&paper_Id='
METADATA_SPREADSHEET = 'https://camps.aptaracorp.com/ACMConference/downloadmetadata.html?proceedingId=' + CONF_ID
PROC_PAGE = 'https://camps.aptaracorp.com/ACMConference/showcopyrightpapers.html?proceeding_ID=' + CONF_ID + '&event_id=15896&workshop_id=0'

USER_LOGINNAME = os.environ.get('TAPS_USER') or input("TAPS user; ")
PASSWORD = os.environ.get('TAPS_PASSWORD') or getpass.getpass("TAPS password: ")
LIST_FILE = "taps_procs.csv"


# ############ Helper functions ##################

def file_is_current(file_path, max_seconds=300):
    if not os.path.exists(file_path):
        return False
    file_mtime = os.path.getmtime(file_path)
    current_time = time.time()
    return (current_time - file_mtime) < max_seconds


def get_pdf(element):
    try:
        s = element.xpath("a/img[@title = 'PDF Open']")[0].attrib['onclick']
        x = re.match(r".*openfile\(('.*')\)", s).groups()[0]
        components = list(map(lambda s: s.strip("'"), x.split(',')))
        url = "https://camps.aptaracorp.com/" + components[1] + "/" + components[2]
    except IndexError: # no PDF link
        url = ""
    return url
    
def get_html(element):
    try:
        s = element.xpath("a/img[@title = 'View HTML']")[0].attrib['onclick']
        x = re.match(r".*showhtml5\(('.*')\)", s).groups()[0]
        components = list(map(lambda s: s.strip("'"), x.split(',')))
        url = "https://camps.aptaracorp.com/" + components[1] + "/" + components[2]
    except IndexError: # no PDF link
        url = ""
    return url

def get_status(element):
    img = element.getchildren()[0]
    try:
        percent = int(re.findall(r"[0-9]+", img.attrib['src'])[0])
    except ValueError:
        percent = None
    return percent

def get_error(element):
    try:
        s = element.xpath("a/img[@title = 'Error/Warning']")[0].attrib['onclick']
        x = re.match(r".*showerrorlog\(('.*')\)", s).groups()[0]
        components = list(map(lambda s: s.strip("'"), x.split(',')))
        proc_id, paper_id, strip_acronym, filename, uid = components
        url = f"https://camps.aptaracorp.com/ACMConference/downloadpdf2.html?Proceeding_ID={proc_id}&Paper_ID={paper_id}&Strip_acronym={strip_acronym}&filename={filename}&uid={uid}&event_id=14600&workshop_id=0"
    except IndexError: # no error link
        url = ""
    return url


# ########### functions #################

def get_submissions(overwrite=True):
    if overwrite is False and os.path.exists(LIST_FILE):
        print("file already exists - skipping download")
        return
    if file_is_current(LIST_FILE):
        print("file downloaded within last 5 minutes - skipping download")
        return

    print("Logging in...")
    session = requests.Session()
    r = session.get(SESSION_PAGE)
    # select_dashboard: 1 = Proceedings, 2 = PACM
    r = session.post(LOGIN_PAGE, data={'user_loginname': USER_LOGINNAME, 'password': PASSWORD, 'select_dashboard': '1', 'button2': 'Login'})
    print("Retrieving list of papers (might take up to one minute - TAPS is slow) ...")
    r = session.get(PROC_PAGE)
    root = etree.HTML(r.text)
    rows = root.xpath("//table[@id = 'ce_data']/tbody/tr")
    headers = root.xpath("//table[@id = 'ce_data']/thead/tr/th/div")
    print(f"Found {len(rows)} papers.")  # number of papers
    cols = [col.text.strip() for col in headers]

    data = []
    for row in rows:
        assert(len(row) == len(cols))
        d = {}
        for i in range(len(row)):
            # special cases:
            if cols[i] == 'STATUS':
                d["STATUS"] = get_status(row.getchildren()[i])
            elif cols[i] == 'ACTIONS':
                d["PDF_URL"] = get_pdf(row.getchildren()[i])
                d["HTML_URL"] = get_html(row.getchildren()[i])
                d["ERROR_URL"] = get_error(row.getchildren()[i])
            elif row.getchildren()[i].text:
                d[cols[i]] = row.getchildren()[i].text.strip()    
                # FIXME: for some reason, Aptara put some paper titles which start with '"' within a further "<blnk>" element. For these, an empty title is returned. 
                # Not a huge problem, however, as we do not use the title from TAPS anywhere
            else:
                d[cols[i]] = ""
        print(f"getting metadata for paper {d['PAPER ID']} ({d['TITLE']})")
        d["METADATA"] = session.get(METADATA_PAGE+d['PAPER ID']).text
        metadata = d['METADATA'].splitlines()
        d["PCS_ID"] = metadata[9]
        d["DOI"] = metadata[12]
        data.append(d)

    #print(cols)
    cols += ["PDF_URL", "HTML_URL", "ERROR_URL", "METADATA", "PCS_ID", "DOI"]
    cols.remove("ACTIONS")

    with open(LIST_FILE, "w") as fd:
        dw = DictWriter(fd, cols)
        dw.writeheader()
        for row in data:
            dw.writerow(row)
    return data


def download_file(paper_id, url, filename, overwrite="modified"):
    try:
        doc = None
        # avoid unnecessary downloads
        if overwrite == "none":
            if os.path.exists(filename):  # only download if file changed
                tqdm.write("   >... already downloaded")
                return True
        elif overwrite == "modified":
            doc = urlopen(url, timeout=10)
            doc_size = int(doc.getheader("Content-Length"))
            if os.path.exists(filename):  # only download if file changed
                file_size = os.stat(filename).st_size
                if file_size == doc_size:
                    tqdm.write("   >... already downloaded and not changed on server")
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
        print(str(e))
        return False



def download_files(data, filetypes, overwrite=False):
    for filetype in filetypes:
        try:
            os.makedirs(filetype['dir'])
        except FileExistsError:
            print(f"directory '{filetype['dir']}' already exists, writing into it")
    for paper in tqdm(data):
        pcs_id = paper['PCS_ID']
        taps_id = paper['PAPER ID']
        print(f"Paper: {pcs_id} (TAPS ID: {taps_id})")
        for filetype in filetypes:
            if len(paper[filetype['field']]) > 1:
                url = paper[filetype['field']]
                filename = f"{filetype['dir']}/{pcs_id}_{taps_id}.{filetype['ext']}"
                print(f"Retrieving {filetype['ext']} file: {paper[filetype['field']]}")
                download_file(taps_id, url, filename)
            else:
                print("   >... not submitted")


# ## Download HTML and PDF

data = get_submissions()
if data is None:
    data = []
    with open(LIST_FILE, "r") as fd:
        dr = DictReader(fd)
        for row in dr:
            data.append(row)


FILES = [{'field': 'PDF_URL', 'dir': 'TAPS_PDF', 'ext': 'pdf'},
         {'field': 'HTML_URL', 'dir': 'TAPS_HTML', 'ext': 'html'}]

# poor man's argparse
filetypes = []
if "--all" in sys.argv:
    filetypes = FILES
else:
    if "--pdf" in sys.argv:
        filetypes.append(FILES[0])
    if "--html" in sys.argv:
        filetypes.append(FILES[1])
if len(filetypes) == 0:
    sys.exit()


download_files(data, filetypes)

