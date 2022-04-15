#!/usr/bin/env python3

import sys
import requests
from lxml import etree
from csv import DictWriter


if len(sys.argv) > 1:
    CONF_ID = int(sys.argv[1])
else:
    CONF_ID = int(input("Conference ID (e.g. 12337): "))

URL=f"https://acmsubmit.acm.org/atyponListing.cfm?proceedingID={CONF_ID}"
content = requests.get(URL).text
root = etree.HTML(content)
rows = root.xpath("//table[@id = 'publications']/tr")
print(f"Found {len(rows)} submissions (including excluded ones).")

# just in case someone needs it:
#headers = root.xpath("//table[@id = 'publications']/thead/tr/th")
#fields = [header.text for header in headers]

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

already_uploaded = [d['File Descriptions'] for d in submissions if not d['excluded']]
excluded = [d['File Descriptions'] for d in submissions if d['excluded']]

filename = f"Supplementary Materials Uploaded to ACM DL ({CONF_ID}).csv"
with open(filename, "w") as fd:
    dw = DictWriter(fd, submissions[0].keys())
    dw.writeheader()
    dw.writerows(submissions)
print(f"Wrote {len(submissions)} submissions to '{filename}'")
