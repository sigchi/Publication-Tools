# ACM-Publication-Tools
Unofficial information and tools for publication chairs at ACM conferences (especially SIGCHI)

# General Workflow

The tools in this repository support the following workflow, as employed for major SIGCHI conferences, such as CHI.

The general publication workflow there:

- paper submission happens via PCS
- authors of accepted papers upload their source files (TeX or Word) to TAPS 
- TAPS generates HTML and PDF versions
- authors check the generated output, modify the source files, re-compile,  and approve the final versions
- authors are required to manually make the final PDFs 'accessible' and upload them to PCS
- authors also upload all further materials (videos, subtitles, supplementary materials) to PCS

Once these steps have been completed for a conference track, the publications team needs to do the following:

- check for missing uploads
- download all files from PCS
- check whether the PDF files in PCS are really the final versions
- check for major formatting problems (wrong template, wrong DOI, missing author information, ...)
- check videos for problems
- check supplementary materials for problematic content
- upload all supplementary files and videos via ACMs upload portal (and remove any uploads that authors might have made)
- provide all final PDF versions to Aptara (TAPS) so that they can provide them to ACM
- (automatically generate lists and documents from metadata)

# Tools

## pcs.py - download files from PCS and sort them

This Python script helps with checking the state of files in PCS, automatically downloading files from PCS, naming them appropriately, and sorting them into folders.


## taps.py

This Python script helps with downloading metadata, PDF files, and HTML files from TAPS.


## lint.py

This Python script checks PDF files from PCS for common formatting problems.


## atypon.py

This Python script downloads and uploafs supplementary files from/to ACMs Atypon system.


## check_video.py

This Python script checks the properties of video files
