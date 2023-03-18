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
import os
import sys
from csv import DictWriter, DictReader
import getpass
from urllib.request import urlretrieve, HTTPError

# additional
import requests


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

def get_submissions(overwrite=False):
    if overwrite is False and os.path.exists(LIST_FILE):
        print("file already exists - skipping download")
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
            else:
                d[cols[i]] = ""
        print(f"getting metadata for paper {d['PAPER ID']} ({d['TITLE']})")
        d["METADATA"] = session.get(METADATA_PAGE+d['PAPER ID']).text
        metadata = d['METADATA'].splitlines()
        d["PCS_ID"] = metadata[9]
        d["DOI"] = metadata[12]
        data.append(d)

    print(cols)
    cols += ["PDF_URL", "HTML_URL", "ERROR_URL", "METADATA", "PCS_ID", "DOI"]
    cols.remove("ACTIONS")

    with open(LIST_FILE, "w") as fd:
        dw = DictWriter(fd, cols)
        dw.writeheader()
        for row in data:
            dw.writerow(row)
    return data


def download_files(data, filetypes, overwrite=False):
    for filetype in filetypes:
        try:
            os.makedirs(filetype['dir'])
        except FileExistsError:
            print(f"directory '{filetype['dir']}' already exists, writing into it")
    for paper in data:
        #pcs_id = paper['METADATA'].splitlines()[9]
        pcs_id = paper['PCS_ID']
        taps_id = paper['PAPER ID']
        print(f"Paper: {pcs_id} (TAPS ID: {taps_id})")
        for filetype in filetypes:
            if len(paper[filetype['field']]) > 1:
                url = paper[filetype['field']]
                filename = f"{filetype['dir']}/{pcs_id}_{taps_id}.{filetype['ext']}"
                if os.path.exists(filename) and not overwrite:
                    print(f"{filename} already exists. Skipping...")
                else:
                    print(f"Retrieving {filetype['ext']} file: {paper[filetype['field']]}")
                    try:
                        urlretrieve(paper[filetype['field']], f"{filetype['dir']}/{pcs_id}_{taps_id}.{filetype['ext']}")
                    except (ValueError, HTTPError):
                        print("   >... not found on server")
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

