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


def find_account_by_card_number(card_number):
    for bank in credit_cards:
        if card_number in credit_cards[bank]:
            return f'Liabilities:Card:{bank}:{card_number}'
    for bank in debit_cards:
        if card_number in debit_cards[bank]:
            return f'Assets:Card:{bank}:{card_number}'
    return None
