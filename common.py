import fitz
from china_bean_importers.secret import *

def open_pdf(name):
    doc = fitz.open(name)
    if doc.is_encrypted:
        for password in pdf_passwords:
            doc.authenticate(password)
        if doc.is_encrypted:
            return None
    return doc