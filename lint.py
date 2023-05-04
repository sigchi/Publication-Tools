#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script checks for typical problems in the camera-ready version 
of papers. It assumes that HTML files from TAPS are in "./TAPS_HTML/" and PDF 
files from PCS are in "./${track_id}_PDF/"

Possible problems are printed on stdout.
Many of them are false positives caused by the inherently difficult extraction of structured
text from PDF files. Please check manually.

"""

##################################

# stdlib
import os
import re
import sys
import glob
import shutil
from csv import DictReader, DictWriter
from lxml import etree, html

# additional
from tqdm import tqdm
import pdfminer
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.high_level import extract_text
from pdfminer.pdftypes import resolve1

# replace print function with tqdm
#print = tqdm.write

def print(thing, end="\n"):
    tqdm.write(str(thing), end=end)

OUTPUT_DIR = "LINTER_RESULTS"
SORT_FILES = True  # sort files with failed checks in subfolders per check (warning: may lead to many duplicates of each file)
# SORT_FILES = False  # do not sort files in subfolders per check


def stringify_list(a_list):
    if len(a_list) == 0:
        return ""
    text = ""
    for line in a_list[:-1]:
        line = line.strip()
        if line.endswith("-"):
            text += line[:-1]
        elif "https" in line:  # make sure that our DOI stays intact
            text += line
        else:
            text += line + " "
    text += a_list[-1].strip()
    return text


def get_info_from_html(html_file):
    info = {}
    try:
        root = html.parse(html_file)
    except OSError:
        print(f"    file not found: {html_file}")
        return info
    body = root.xpath("//section[@class = 'body']")[0]
    # print(body.text_content())
    info['CHARACTER COUNT'] = len(body.text_content())
    info['WORD COUNT'] = len(body.text_content().split())
    
    title = root.xpath("//title")[0]
    info['TITLE'] = title.text_content()
     
    # too hard - seems inconsistent.
    concepts = root.xpath("//ccs2012")
    if len(concepts) == 1: # TODO: check when len is not 1
        concept_list = (re.findall('CCS Concepts: (.*?;)+', concepts[0].text_content()))
        info['CCS CONCEPTS'] = "".join(concept_list)
    else:
        print(f"# {html_file}: concepts not found")
    
    doi = root.xpath("//div[@class = 'pubInfo']//a")[0] # 1 would be proceedings DOI
    info['DOI'] = doi.text_content()
    
    keywords = root.xpath("//div[@class='classifications']//span[@class = 'keyword']/small")
    info['KEYWORDS'] = "; ".join([k.text_content() for k in keywords])
    
    authors = root.xpath("//div[@class = 'authorGroup']/div[@class = 'author']")
    info['AUTHOR COUNT'] = len(authors)
    info['AUTHORS'] = [author.text_content().replace("\r\n", "").split(",") for author in authors]
    
    figures = root.xpath("//figure")
    info['FIGURE COUNT'] = len(figures)
    
    tables = root.xpath("//table[@class = 'table']")
    info['TABLE COUNT'] = len(tables)
    
    references = root.xpath("//ul[@class = 'bibUl']/li")
    info['REFERENCE COUNT'] = len(references)

    return(info)



def extract_html_text(html_file):
    try:
        root = html.parse(html_file)
    except OSError:
        print(f"file not found: {html_file}")
        return ""       
    body = root.xpath("//section[@class = 'body']")[0]
    return body.text_content()



def get_info_from_pdf(pdf_file, debug = False):
    pdf_info = {}
    doc = PDFDocument(PDFParser(open(pdf_file, 'rb')))
    pdf_info["EMBEDDED FILES"] = False
    try:
        for xref in doc.xrefs:
            for objid in xref.get_objids():
                obj = doc.getobj(objid)
                if str(obj.get("Type")) == "/'Filespec'":
                    pdf_info["EMBEDDED FILES"] = True
    except AttributeError:
        pass
    pdf_properties = doc.info[0]
    if 'Creator' in pdf_properties:
        if pdf_properties['Creator'][0] in [0xfe, 0xff]:
            pdf_info['PDF CREATOR'] = pdf_properties['Creator'].decode('utf-16')
        else:
            pdf_info['PDF CREATOR'] = pdf_properties['Creator'].decode('utf-8')
    else:
        pdf_info['PDF CREATOR'] = ""
    if 'Producer' in pdf_properties:
        if pdf_properties['Producer'][0] in [0xfe, 0xff]:
            pdf_info['PDF PRODUCER'] = pdf_properties['Producer'].decode('utf-16')
        else:
            pdf_info['PDF PRODUCER'] = pdf_properties['Producer'].decode('utf-8')
    else:
        pdf_info['PDF PRODUCER'] = ""

    text = extract_text(pdf_file)
    references = text[text.find("REFERENCES"):]
    num_references = len(re.findall(r'(^\[[0-9]+\] .*)', references, re.MULTILINE))

    # states
    TITLE = 0
    AUTHORS = 1
    ABSTRACT = 2
    CCS_CONCEPTS = 3
    KEYWORDS = 4
    ACM_REF = 5 
    COPYRIGHT = 6  # can appear between other blocks
    BODY = 7
    DONE = 99


    title = []
    authors = [[]]
    abstract = []
    ccs_concepts = []
    keywords = []
    acm_ref = []
    copyright = []

    state = TITLE
    prev_state = TITLE
    for line in text.splitlines():
        if line.startswith("1 ") and len(acm_ref) > 0: 
            break # we have really reached the first line    
        if line.startswith("Permission to make") or line.startswith("This work is licensed"):
            prev_state = state
            state = COPYRIGHT
        if line.startswith("ABSTRACT"):
            state = ABSTRACT
            continue
        elif line.startswith("CCS CONCEPTS"):
            state = CCS_CONCEPTS
            continue
        elif line.startswith("KEYWORDS"):
            state = KEYWORDS
            continue
        elif line.startswith("ACM Reference Format"):
            state = ACM_REF
            continue
        if debug:
            print(state, line) # debug

        if state == ABSTRACT:
            abstract.append(line.strip())
        elif state == CCS_CONCEPTS:
            ccs_concepts.append(line.strip())
        elif state == KEYWORDS:
            keywords.append(line.strip())
        elif state == ACM_REF:
            if len(line) > 1:
                acm_ref.append(line.strip())
        elif state == COPYRIGHT:
            if len(line) > 1:
                copyright.append(line.strip())
            if line.startswith('https://doi.org'): # end of copyright block
                state = prev_state
        elif state == TITLE: # 
            if len(line) > 1:
                title.append(line.strip())
            else:
                state = AUTHORS
        elif state == AUTHORS: # should be last check
            if len(line) > 1:
                authors[-1].append(line.strip().rstrip('-'))
            else:
                authors.append([])

    pdf_info['AUTHORS'] = authors[0:-1] # drop the last, empty author
    pdf_info['AUTHOR COUNT'] = len(authors[0:-1])
    pdf_info['TITLE'] = stringify_list(title)
    pdf_info['ACM REF'] = stringify_list(acm_ref)
    pdf_info['KEYWORDS'] = stringify_list(keywords)
    pdf_info['CCS CONCEPTS'] = stringify_list(ccs_concepts)
    if doi := re.search(r'(https://doi.org/10.1145/[0-9\.]+)', stringify_list(acm_ref)):
        pdf_info['DOI'] = doi.groups()[0]
    else:
        pdf_info['DOI'] = ""
    pdf_info['REFERENCE COUNT'] = num_references
    pdf_info['CHARACTER COUNT'] = len(text)
    pdf_info['WORD COUNT'] = len(text.split())
    pdf_info['COPYRIGHT'] = stringify_list(copyright)
    
    return pdf_info


def get_pdf_catalog(pdf_file):
    fp = open(pdf_file, 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    catalog = doc.catalog
    return catalog


# Attention: some of the checks below don't work very well due to difficulties in extracting text from PDF

def check_pdf_difference_taps_pdf(data):
    pcs_size = os.stat(data["pdf_file"]).st_size
    taps_size = os.stat(data["taps_pdf_file"]).st_size
    if pcs_size == taps_size:
        return "File sizes in TAPS and PCS are identical - probably no accessibility check done."
    if pcs_size / taps_size > 1.2 or pcs_size / taps_size < 0.8:
        return f"File sizes in TAPS ({taps_size/1000000.0:.2f} MB.) and PCS ({pcs_size/1000000.0:.2f} MB). differ by more than 20% - maybe not the same file."


def check_pdf_size(data):
    pcs_size = os.stat(data["pdf_file"]).st_size
    if pcs_size > 1000*1000*70:
        return f"PDF file larger than 70 MB: {pcs_size/1000000.0:.2f} MB."
    if pcs_size < 1000*100:
        return f"PDF file smaller than 100 kB - maybe corrupted: {pcs_size/1000000.0:.2f} MB."


# works reliably
def check_form_fields(data):
    try:
        fields = resolve1(data['pdf_catalog']['AcroForm'])['Fields']
        if len(fields) > 0:
            return "The paper contains form fields."
    except:
        return


# works reliably
def check_embedded_files(data):
    if data['pdf_info']['EMBEDDED FILES']:
        return f"PDF contains embedded files (typically reports from the Acrobat accessibility checker."


# works reliably
def check_ligatures_fi(data):
    if data['html_text'].find("fi") != -1 and data['pdf_text'].find("fi") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'fi' (but HTML does). Please check whether ligatures are encoded correctly."


# works reliably
def check_ligatures_ff(data):
    if data['html_text'].find("ff") != -1 and data['pdf_text'].find("ff") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'ff' (but HTML does). Please check whether ligatures are encoded correctly."


# works reliably
def check_ligatures_qu(data):
    if data['html_text'].find("Qu") != -1 and data['pdf_text'].find("Qu") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'Qu' (but HTML does). Please check whether ligatures are encoded correctly."


TAPS_PDF_CREATORS = ['LaTeX with acmart 2022/10/24 v1.88 Typesetting articles for the Association for Computing Machinery and hyperref 2022-02-21 v7.00n Hypertext links for LaTeX', 
                     'LaTeX with acmart 2023/03/30 v1.90 Typesetting articles for the Association for Computing Machinery and hyperref 2022-02-21 v7.00n Hypertext links for LaTeX',
                     'LaTeX with hyperref']
# extracts info reliably but it seems that a different PDF Creator may also be caused by TAPS staff
def check_pdf_creator(data):
    if data['pdf_info']['PDF CREATOR'] not in TAPS_PDF_CREATORS:
        return f"This PDF has not been generated by TAPS ('Producer' field in metadata says: {data['pdf_info']['PDF CREATOR']})"


def get_doi_list(csvfile):
    doi = {}
    with open(csvfile) as fd:
        dr = DictReader(fd)
        for paper in dr:
            doi[paper['PCS_ID']] = paper['DOI']            
    return doi


DOI = get_doi_list('./taps_procs.csv')


# works semi-reliably - if it finds a wrong DOI, it is usually right
def check_pdf_doi(data):
    pcs_id = data['pcs_id']
    if pcs_id not in DOI:
        return(f"DOI for PCS ID {pcs_id} unknown")
    if data['pdf_info']['DOI'] != DOI[pcs_id]:
        if len(data['pdf_info']['DOI'].strip()) == 0:
            return(f"DOI might be missing in PDF. DOI in HTML file: {DOI[pcs_id]}")
        else:
            return(f"DOI might be wrong in PDF: {data['pdf_info']['DOI']} vs. {DOI[pcs_id]}")


# works reliably
def check_line_length(data):
    line_lengths = [len(line) for line in data['pdf_text'].splitlines()]
    line_count = len(line_lengths)
    median = sorted(line_lengths)[line_count//2]
    # print(f"Median line length: {median}")
    if median > 60 + 20:  # median line length in two columns: 60 - 65 chars
        return f"Single-column format or incorrectly tagged PDF (median line length is {median})."
    elif median < 40:  # median line length in two columns: 60 - 65 chars
        return f"Strange! Median line length is less than 40 ({median}) - which should not happen in the ACM two-column layout."


# unreliable
def check_differences_reference_count(data):
    hr = data['html_info']['REFERENCE COUNT']
    pr = data['pdf_info']['REFERENCE COUNT']
    if hr != pr:
        return f"Different number of references found in HTML ({hr}) and PDF ({pr}). Please check."


# unreliable
def check_differences_author_count(data):
    ha = data['html_info']['AUTHOR COUNT']
    pa = data['pdf_info']['AUTHOR COUNT']
    if ha != pa:
        return f"Different number of authors found in HTML ({ha}) and PDF ({pa}). Probably a parsing error of our script. Please check."


# mostly reliable - however, many false positives due to "accessibility" problem
def check_differences_title(data):
    ht = data['html_info']['TITLE'].strip()
    pt = data['pdf_info']['TITLE'].strip()
    pt = pt[0:min(len(pt), len(ht))]  # pdf title sometimes contains content from next line
    ht_clean = ht.replace("’", "'").replace('“', '"').replace('”', '"')
    pt_clean = pt.replace("’", "'").replace('“', '"').replace('”', '"')
    if ht_clean != pt_clean:
        return f"Different titles in HTML and PDF. Please check:\n    {ht}\n    {pt}"   


# quite reliable - some false positives
def check_email(data):
    authors = data['pdf_info']['AUTHORS']
    num_authors = data['pdf_info']['AUTHOR COUNT']
    emails = 0
    for author in authors:
        for line in author:
            if "@" in line:
                emails += 1
    if emails == 0:
        return "None of the authors has an email address given!"
    elif emails < num_authors:
        pass # too many false positives
        #return f"Only {emails}/{num_authors} authors have an email address!"


CHECKS = [check_embedded_files, check_line_length, check_differences_title, check_email, 
          check_ligatures_fi, check_ligatures_ff, check_ligatures_qu, check_pdf_creator, 
          check_differences_reference_count, check_pdf_doi, check_form_fields, 
          check_pdf_difference_taps_pdf, check_pdf_size]


def lint(pdf_file):
    print(f"# Checking {pdf_file}")
    data = {}
    data["pdf_file"] = pdf_file
    try:
        pcs_id = re.findall(r'[a-z]+[0-9]+', pdf_file.split("/")[-1])[0]
        data["pcs_id"] = pcs_id
    except:
        print(f"{pdf_file}: PCS ID could not be extracted")
        return
    try:
        html_file = glob.glob(f'{HTML_DIR}/{pcs_id}*.html')[0]
        data["html_file"] = html_file
    except:
        print(f"Error: {pdf_file} ({pcs_id}): HTML file not found - aborting")
        errors = {}
        errors["PCS ID"] = pcs_id  #   hand id back to calling function
        errors["PDF file"] = pdf_file  
        errors["Title"] = "TAPS HTML file not found!"  
        raise RuntimeError("TAPS HTML not found")
    try:
        taps_pdf_file = glob.glob(f'{TAPS_PDF_DIR}/{pcs_id}*.pdf')[0]
        data["taps_pdf_file"] = taps_pdf_file
    except:
        print(f"Warning: {pdf_file} ({pcs_id}): TAPS PDF file not found - aborting")
        raise RuntimeError("TAPS PDF not found")
    data["pdf_text"] = extract_text(pdf_file)
    data["pdf_info"] = get_info_from_pdf(pdf_file)
    data["pdf_catalog"] = get_pdf_catalog(pdf_file)
    data["html_text"] = extract_html_text(html_file)
    data["html_info"] = get_info_from_html(html_file)

    errors = {}
    for check in CHECKS:
        error = check(data)
        errors[check.__name__] = error
        if SORT_FILES and error:
            destination_dir = f"{OUTPUT_DIR}/{check.__name__}_failed"
            os.makedirs(destination_dir, exist_ok=True)
            shutil.copy2(pdf_file, destination_dir)
    

    # only check that needs pcs_id
    #errors["check_pdf_doi"] = check_pdf_doi(html_info, html_text, pdf_info, pdf_text, pcs_id)
    # only check that needs PDF catalog
   # errors["check_form_fields"] = check_form_fields(pdf_catalog)
    # only check that needs TAPS PDF
    #errors["check_pdf_difference_taps_pdf"] = check_pdf_difference_taps_pdf(pdf_file, taps_pdf_file)
    # only check that needs only PCS PDF
    #errors["check_pdf_size"] = check_pdf_size(pdf_file)
    if any(errors.values()):
        for typ, message in errors.items():
            if message:
                print(f"{pcs_id}: {typ}: {message}")
    else:
        print(f"#{pcs_id}: OK!")
    errors["PCS ID"] = pcs_id  #   hand id back to calling function
    errors["PDF file"] = pdf_file  
    errors["Title"] = data['pdf_info']['TITLE']  
    return(errors)  


if len(sys.argv) < 2:
    print("Please provide PDF directory as parameter")
    sys.exit(1)

HTML_DIR = "./TAPS_HTML"
# html_files = glob.glob(f'{HTML_DIR}/*.html') # currently we only iterate over the PDF files
TAPS_PDF_DIR = "./TAPS_PDF"

PDF_DIR = None  # also use as flag for whether we check a whole dir

if len(sys.argv) == 2 and not sys.argv[1].endswith(".pdf"):  # directory given
    PDF_DIR = f"{sys.argv[1]}"
    pdf_files = sorted(glob.glob(f'{PDF_DIR}/*.pdf'))
    if len(pdf_files) == 0:
        print(f"No PDF files found in {PDF_DIR}.")
        sys.exit(1)
else:  # individual files given
    pdf_files = sys.argv[1:]


print("# I'm linting!")
error_list = []
for pdf_file in tqdm(pdf_files):
    try:
        error_list.append(lint(pdf_file))
        print("")
    except Exception as e:
        print(f'{pdf_file} couldn\'t be to automatically checked: ', end="")
        print(e)
        error_list.append({'PDF file': pdf_file})
    if PDF_DIR:
        with open(f"{PDF_DIR.strip('/').replace('/','_')}.lint.csv", 'w') as fd:
            dw = DictWriter(fd, error_list[0].keys(), restval='x')
            dw.writeheader()
            dw.writerows(error_list)
