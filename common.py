import re
import sys
import fitz

card_tail_pattern = re.compile('.*银行.*\(([0-9]{4})\)')

def match_card_tail(src):
    m = card_tail_pattern.match(src)
    return m[1] if m else None


def open_pdf(config, name):
    doc = fitz.open(name)
    if doc.is_encrypted:
        for password in config['pdf_passwords']:
            doc.authenticate(password)
        if doc.is_encrypted:
            return None
    return doc


def find_account_by_card_number(config, card_number):

    for prefix, accounts in config['card_accounts'].items():
        for bank, numbers in accounts.items():
            if card_number in numbers:
                return f'{prefix}:{bank}:{card_number}'

    return None


def find_destination_account(config, src, expense):

    for key in config['destination_accounts']:
        if key in src:
            return config['destination_accounts'][key]

    return config['unknown_expense_account'] if expense else config['unknown_income_account']


def my_assert(cond, msg, lineno, row):
        assert cond, f"{msg} on line {lineno}:\n{row}"

def my_warn(msg, lineno, row):
    print(f"WARNING: {msg} on line {lineno}:\n{row}\n", file=sys.stderr)
