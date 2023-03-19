#!/usr/bin/env python3

# Public Domain / CC-0
# (0) 2022 Raphael Wimmer <raphael.wimmer@ur.de>

INFO = """This script checks for typical problems in the camera-ready version 
of papers. It assumes that HTML files from TAPS are in "./TAPS_HTML/" and PDF 
files from PCS are in "./PCS_PDF/"

Possible problems are printed on stdout.
Many of them are false positives caused by the inherently difficult extraction of structured
text from PDF files. Please check manually.


"""

HTML_DIR = "./TAPS_HTML"
PDF_DIR = "./PCS_PDF"

##################################

print(INFO)

#stdlib
from lxml import etree, html
import re
import glob
from csv import DictReader

# additional
import pdfminer
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.high_level import extract_text
from pdfminer.pdftypes import resolve1


# for testing purposes
TEST_PDF = './PCS_PDF/pn1193.pdf'
TEST_HTML = './TAPS_HTML/pn1193_191.html'


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
    print("#get_info_from_html()")
    info = {}
    try:
        root = html.parse(html_file)
    except OSError:
        print(f"    file not found: {html_file}")
        return info        
    body = root.xpath("//section[@class = 'body']")[0]
    #print(body.text_content())   
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
    print("#extract_html_text()")
    try:
        root = html.parse(html_file)
    except OSError:
        print(f"file not found: {html_file}")
        return ""       
    body = root.xpath("//section[@class = 'body']")[0]
    return body.text_content()



def get_info_from_pdf(pdf_file, debug = False):
    print("#get_info_from_pdf()")
    
    pdf_info = {}
    pdf_properties = PDFDocument(PDFParser(open(pdf_file, 'rb'))).info[0]
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
    print("#get_pdf_catalog()()")
    fp = open(pdf_file, 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    catalog = doc.catalog
    return catalog


# Attention: most of the checks below don't work very well due to difficulties in extracting text from PDF

def check_form_fields(pdf_catalog):
    try:
        fields = resolve1(pdf_catalog['AcroForm'])['Fields']
        if len(fields) > 0:
            return "The paper contains form fields."
    except:
        return


def check_ligatures_fi(html_info, html_text, pdf_info, pdf_text):
    if html_text.find("fi") != -1 and pdf_text.find("fi") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'fi' (but HTML does). Please check whether ligatures are encoded correctly."


def check_ligatures_ff(html_info, html_text, pdf_info, pdf_text):
    if html_text.find("ff") != -1 and pdf_text.find("ff") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'ff' (but HTML does). Please check whether ligatures are encoded correctly."

def check_ligatures_qu(html_info, html_text, pdf_info, pdf_text):
    if html_text.find("Qu") != -1 and pdf_text.find("Qu") == -1:
        return "Accessibility: the PDF plain text does not contain the letters 'Qu' (but HTML does). Please check whether ligatures are encoded correctly."



def check_pdf_creator(html_info, html_text, pdf_info, pdf_text):
    if pdf_info['PDF CREATOR'] not in ['LaTeX with acmart 2022/10/24 v1.88 Typesetting articles for the Association for Computing Machinery and hyperref 2022-02-21 v7.00n Hypertext links for LaTeX', 'LaTeX with hyperref']:
        return f"This PDF has not been generated by TAPS ('Producer' field in metadata says: {pdf_info['PDF CREATOR']})"


def get_doi_list(csvfile):
    doi = {}
    with open(csvfile) as fd:
        dr = DictReader(fd)
        for paper in dr:
            doi[paper['PCS_ID']] = paper['DOI']
            
    return doi

DOI = get_doi_list('./taps_procs.csv')

def check_pdf_doi(html_info, html_text, pdf_info, pdf_text, pcs_id):
    if not pcs_id in DOI:
        return(f"DOI for PCS ID {pcs_id} unknown")
    if pdf_info['DOI'] != DOI[pcs_id]:
        return(f"DOI might be wrong in PDF: {pdf_info['DOI']} vs. {DOI[pcs_id]}")


def check_differences_reference_count(html_info, html_text, pdf_info, pdf_text):
    hr = html_info['REFERENCE COUNT']
    pr = pdf_info['REFERENCE COUNT']
    if hr != pr:
        return f"Different number of references found in HTML ({hr}) and PDF ({pr}). Please check."

def check_differences_author_count(html_info, html_text, pdf_info, pdf_text):
    ha = html_info['AUTHOR COUNT']
    pa = pdf_info['AUTHOR COUNT']
    if ha != pa:
        return f"Different number of authors found in HTML ({ha}) and PDF ({pa}). Probably a parsing error of our script. Please check."

def check_differences_title(html_info, html_text, pdf_info, pdf_text):    
    ht = html_info['TITLE'].strip()
    pt = pdf_info['TITLE'].strip()
    pt = pt[0:min(len(pt), len(ht))] # pdf title sometimes contains content from next line
    ht_clean = ht.replace("’", "'").replace('“', '"').replace('”', '"')
    pt_clean = pt.replace("’", "'").replace('“', '"').replace('”', '"')
    if ht_clean != pt_clean:
        return f"Different titles in HTML and PDF. Please check:\n{ht}\n{pt}"   


def check_email(html_info, html_text, pdf_info, pdf_text):
    authors = pdf_info['AUTHORS']
    num_authors = pdf_info['AUTHOR COUNT']
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


CHECKS = [check_differences_title, check_email, check_ligatures_fi, check_ligatures_ff, check_ligatures_qu, check_pdf_creator, check_differences_reference_count]


def lint(pdf_file):
    print(f"# Checking {pdf_file}")
    try:
        pcs_id = re.findall(r'pn[0-9]+', pdf_file)[0]
    except:
        print(f"{pdf_file}: PCS ID could not be extracted")
        return
    try:
        html_file = glob.glob(f'{HTML_DIR}/{pcs_id}*.html')[0]
    except:
        print(f"{pdf_file}: HTML file not found")
        return
    print("#extract_text()")
    pdf_text = extract_text(pdf_file)
    pdf_info = get_info_from_pdf(pdf_file)
    pdf_catalog = get_pdf_catalog(pdf_file)
    html_text = extract_html_text(html_file)
    html_info = get_info_from_html(html_file)
    errors = []
    for check in CHECKS:
        ret = check(html_info, html_text, pdf_info, pdf_text)
        if ret:
            errors.append(ret)
    # only check that needs pcs_id        
    ret = check_pdf_doi(html_info, html_text, pdf_info, pdf_text, pcs_id)
    if ret:
            errors.append(ret)
    ret = check_form_fields(pdf_catalog)
    if ret:
            errors.append(ret)

    if len(errors) > 0:
        print(f"{pcs_id}: ", end="")
        print(f"\n{pcs_id}: ".join(errors))
    else:
        print(f"#{pcs_id}: OK!")
        pass


pdf_files = sorted(glob.glob(f'{PDF_DIR}/*.pdf'))
#html_files = glob.glob(f'{HTML_DIR}/*.html') # currently we only iterate over the PDF files

print("# I'm linting!")
for pdf_file in pdf_files:
    try:
        lint(pdf_file)
        print("")
    except Exception as e:
        print(f'{pdf_file} couldn\'t be to automatically checked: ', end="")
        print(e)



