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

ATTENTION: existing files are overwritten.
"""

CHI_2021_ID = '11385'
CHI_2021_EA_ID = '11384'
CHI_2022_ID = '12338'
CHI_2022_EA_ID = '12337'


CONF_ID = str(CHI_2022_ID)

##################################

print(INFO)


# stdlib
from lxml import etree
import re
import os
import sys
from csv import DictWriter
import getpass
from urllib.request import urlretrieve, HTTPError

# additional
import requests


SESSION_PAGE = 'https://camps.aptaracorp.com/ACMConference/'
LOGIN_PAGE = 'https://camps.aptaracorp.com/ACMConference/login.html'
METADATA_PAGE = 'https://camps.aptaracorp.com/ACMConference/showpaperdetails.html?proceeding_ID=' + CONF_ID + '&paper_Id='
PROC_PAGE = 'https://camps.aptaracorp.com/ACMConference/showcopyrightpapers.html?proceeding_ID=' + CONF_ID + '&event_id=14600&workshop_id=0'

USER_LOGINNAME = os.environ.get('TAPS_USER') or input("TAPS user; ")
PASSWORD = os.environ.get('TAPS_PASSWORD') or getpass.getpass("TAPS password: ")


print("Logging in...")
session = requests.Session()
r = session.get(SESSION_PAGE)
r = session.post(LOGIN_PAGE, data={'user_loginname': USER_LOGINNAME, 'password': PASSWORD, 'button2': 'Login'})


print("Retrieving list of papers (might take up to one minute - TAPS is slow) ...")
r = session.get(PROC_PAGE)


root = etree.HTML(r.text)

rows = root.xpath("//table[@id = 'ce_data']/tbody/tr")
headers = root.xpath("//table[@id = 'ce_data']/thead/tr/th/div")
print(f"Found {len(rows)} papers.") # number of papers
cols = [col.text.strip() for col in headers]


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
    #https://camps.aptaracorp.com/ACMConference/downloadpdf2.html?Proceeding_ID=12338&Paper_ID=1&Strip_acronym=chi22&filename=ValidationError.html&uid=5451e4b5-4cc3-11ec-b613-166a08e17233&event_id=14600&workshop_id=0
    #;showerrorlog('12338','2','chi22','ValidationError.html','1b0362c5-4b97-11ec-b613-166a08e17233')"
    try:
        s = element.xpath("a/img[@title = 'Error/Warning']")[0].attrib['onclick']
        x = re.match(r".*showerrorlog\(('.*')\)", s).groups()[0]
        components = list(map(lambda s: s.strip("'"), x.split(',')))
        proc_id, paper_id, strip_acronym, filename, uid = components
        url = f"https://camps.aptaracorp.com/ACMConference/downloadpdf2.html?Proceeding_ID={proc_id}&Paper_ID={paper_id}&Strip_acronym={strip_acronym}&filename={filename}&uid={uid}&event_id=14600&workshop_id=0"
    except IndexError: # no error link
        url = ""
    return url


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


cols += ["PDF_URL", "HTML_URL", "ERROR_URL", "METADATA", "PCS_ID", "DOI"]
cols.remove("ACTIONS")


with open("taps_procs.csv", "w") as fd:
    dw = DictWriter(fd, cols)
    dw.writeheader()
    for row in data:
        dw.writerow(row)


# ## Download HTML and PDF

FILES = [{'field': 'PDF_URL', 'dir': 'TAPS_PDF', 'ext': 'pdf'},
         {'field': 'HTML_URL', 'dir': 'TAPS_HTML', 'ext': 'html'}]

filetypes = [] 

# poor man's argparse
if "--all" in sys.argv:
    filetypes = FILES
else:
    if "--pdf" in sys.argv:
        filetypes.append(FILES[0])
    if "--html" in sys.argv:
        filetypes.append(FILES[1])
if len(filetypes) == 0:
    sys.exit()
        
for filetype in filetypes:
    try:
        os.makedirs(filetype['dir'])
    except FileExistsError:
        print(f"directory '{filetype['dir']}' already exists, writing into it")


for paper in data:
    pcs_id = paper['METADATA'].splitlines()[9]
    print(f"Paper: {pcs_id} (TAPS ID: {paper['PAPER ID']})")
    for filetype in filetypes:
        if len(paper[filetype['field']]) > 1:
            print(f"Retrieving {filetype['ext']} file: {paper[filetype['field']]}")
            try:
                urlretrieve(paper[filetype['field']], f"{filetype['dir']}/{pcs_id}_{paper['PAPER ID']}.{filetype['ext']}" )
            except (ValueError, HTTPError):
                print("   >... not found on server")
        else:
            print("   >... not submitted")


