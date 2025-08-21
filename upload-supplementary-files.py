#!/usr/bin/env python3

# SPDX-License-Identifier: CC0-1.0
# (0) 2025 Sven Mayer <info@sven-mayer.com>

import yaml
import json
import time
import os

import tqdm 
import pandas as pd

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


import os, time
import undetected_chromedriver as uc

def setupDriver(outputFolder="./downloads", profile_dir="~/uc-profile"):
    """
    Set up the Chrome WebDriver with the specified options.

    Parameters
    ----------
    outputFolder : str
        The folder where downloaded files will be saved.
    profile_dir : str
        The directory for the Chrome user profile.

    Returns
    -------
    uc.Chrome
        The configured Chrome WebDriver instance.
    """
    profile_dir = os.path.abspath(os.path.expanduser(profile_dir))
    os.makedirs(profile_dir, exist_ok=True)  # ensure writable

    opts = uc.ChromeOptions()
    # Allow 3rd-party cookies in iframes (for your uploader)
    opts.add_argument("--disable-features=BlockThirdPartyCookies,ThirdPartyStoragePartitioning,CookieDeprecationLabels")
    opts.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(outputFolder),
        "profile.block_third_party_cookies": False,
        "profile.cookie_controls_mode": 0,
        "profile.default_content_setting_values.cookies": 1,
    })

    # Use a dedicated profile outside Dropbox to avoid file locks:
    opts.add_argument(f"--user-data-dir={profile_dir}")
    # Startup hygiene (prevents some macOS first-run dialogs)
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-component-extensions-with-background-pages")
    opts.add_argument("--disable-gpu")  # harmless on mac; avoids some GPU init issues

    # Pin to your installed Chrome major version (your UA shows 139)
    driver = uc.Chrome(
        options=opts,
        version_main=139  # adjust if your Chrome is a different major
        # ,headless=False   # optional; keep headful while debugging
        # ,use_subprocess=True  # can help on some mac setups
    )

    driver.maximize_window()
    return driver


def upload(e, proceedings_parent, uploader_name, uploader_email):
    """
    Upload a supplementary file to the ACM submission system.

    Parameters
    ----------
    e : object
        The artifact entity containing metadata and file paths.
    proceedings_parent : str
        The parent ID for the proceedings.
    uploader_name : str
        The name of the person uploading the file.
    uploader_email : str
        The email of the person uploading the file.

    Returns
    -------
    bool
        True if the upload was successful, False otherwise.
    """

    if type(e.Type) != str:
        print(f" * {e.DOI}: Invalid type for e.Type: {type(e.Type)}")
        return False
    if e.Type == "video":
        supplement_type = 'Video'
    else:
        # In case the PCS dropdown options are not aligned with the ACM upload fields.
        supplement_type = e.Type.capitalize().replace('Presentation', 'Presentation Slides').replace('Other', 'Supplemental Material').replace('other', 'Supplemental Material')

    if e.Path.endswith(".srt"):
        print(f" * {e.DOI}: Invalid file type: .srt they need to be converted to .vtt first")
        return False
    
    abspath = os.path.abspath(f'{e.Path}')
    if os.path.exists(abspath) == False:
        print(f" * {e.DOI}: File not found: {abspath}")
        return False
    


    URL = f"https://cms.acm.org/artifactSubmission/fileUpload.cfm?parent={proceedings_parent}"
    driver.get(URL)
    time.sleep(5)

    ePaperDOI = driver.find_element(by=By.ID, value="paperDOI")
    ePaperDOI.clear()
    ePaperDOI.send_keys(e.DOI)
    time.sleep(0.5)

    eUserName = driver.find_element(by=By.ID, value="inputUserName")
    eUserName.clear()
    eUserName.send_keys(uploader_name)
    time.sleep(0.5)

    eUserEmail = driver.find_element(by=By.ID, value="inputUserEmail")
    eUserEmail.clear()
    eUserEmail.send_keys(uploader_email)
    time.sleep(0.5)

    eTitle = driver.find_element(by=By.ID, value="title")
    eTitle.clear()
    eTitle.send_keys(e.Title)
    time.sleep(0.5)

    eFileType = driver.find_element(by=By.ID, value="fileType")
    eFileType.send_keys(supplement_type)
    time.sleep(0.5)

    eDescription = driver.find_element(by=By.ID, value="description")
    eDescription.clear()
    eDescription.send_keys(e.Description)
    time.sleep(0.5)

    iframe = driver.find_element(By.CLASS_NAME, "upload-iframe")
    driver.switch_to.frame(iframe)

    eFile = driver.find_element(by=By.ID, value="file")
    eFile.send_keys(abspath)
    time.sleep(0.5)

    driver.switch_to.default_content()

    eUploadButton = []
    while (len(eUploadButton) == 0):
        time.sleep(1)
        eUploadButton = driver.find_elements(by=By.CLASS_NAME, value="remove-upload")
        
    time.sleep(1)

    eSubmitBtn = driver.find_element(by=By.ID, value="submitBtn")
    eSubmitBtn.click()
    time.sleep(2)

    return True

if __name__ == '__main__':
    with open("config.yaml") as f:
        CONFIG = yaml.safe_load(f)
    proceedingsParent = CONFIG["ProceedingsParent"]
    uploader_name = CONFIG["ACM_UPLOADER_NAME"]
    uploader_email = CONFIG["ACM_UPLOADER_EMAIL"]

    if not uploader_email:
        print("Uploader email is not configured in config.json.")
        exit(1)

    if not uploader_name:
        print("Uploader name is not configured in config.json.")
        exit(1)

    if not proceedingsParent:
        print("Proceedings parent is not configured in config.json.")
        exit(1)


    filenameSupplementary = "supFileList.csv"

    if os.path.exists(filenameSupplementary):
        dfArtifacts = pd.read_csv(filenameSupplementary)
    else:
        print(f"File {filenameSupplementary} not found. Please create it with the required columns.")
        exit(1)
    
    required_columns = ["ID", "Path", "DOI", "Title", "Type", "Description", "File"]
    if not all(col in dfArtifacts.columns for col in required_columns):
        print(f"File {filenameSupplementary} is missing required columns.")
        exit(1)

    print("Starting Selenium.")
    driver = setupDriver("./downloads")

    if not "Done" in dfArtifacts.columns:
        dfArtifacts["Done"] = False

    dfToDo = dfArtifacts.sort_values("ID")
    for i, e in tqdm.tqdm(dfToDo.iterrows(), total=len(dfToDo)):
        if e.Done:
            continue
        if upload(e, proceedingsParent, uploader_name, uploader_email):
            dfArtifacts.loc[dfArtifacts.Path == e.Path, "Done"] = True
            dfArtifacts.to_csv("supFileList.csv", index=False)

    print(f"Uploaded {len(dfArtifacts[dfArtifacts.Done])} of {len(dfArtifacts)} files successfully.")