import re
import sys
import typing

import fitz

card_tail_pattern = re.compile('.*银行.*\(([0-9]{4})\)')


class BillDetailMapping(typing.NamedTuple):
    # used to match an item's narration
    narration_keywords: tuple[str]
    # used to match an item's payee
    payee_keywords: tuple[str]
    # destination found
    destination_account: str
    # other metadata to append in bill
    additional_metadata: dict[str, object]

    def match(self, desc: str, payee: str) -> typing.Optional[tuple[str, dict[str, object]]]:
        # match narration first
        if desc is not None:
            for keyword in self.narration_keywords:
                if keyword in desc:
                    return self.destination_account, self.additional_metadata
        # then try payee
        if payee is not None:
            for keyword in self.payee_keywords:
                if keyword in payee:
                    return self.destination_account, self.additional_metadata
        return None


def match_card_tail(src):
    assert (type(src) == str)
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
    if isinstance(card_number, int):
        card_number = str(card_number)
    for prefix, accounts in config['card_accounts'].items():
        for bank, numbers in accounts.items():
            if card_number in numbers:
                return f'{prefix}:{bank}:{card_number}'

    return None


def match_destination_and_metadata(config, desc, payee):
    
    for m in config['detail_mappings']:
        mapping: BillDetailMapping = m
        if dest := mapping.match(desc, payee):
            return dest
    return None


def unknown_account(config, expense) -> str:
    return config['unknown_expense_account'] if expense else config['unknown_income_account']


def my_assert(cond, msg, lineno, row):
    assert cond, f"{msg} on line {lineno}:\n{row}"


def my_warn(msg, lineno, row):
    print(f"WARNING: {msg} on line {lineno}:\n{row}\n", file=sys.stderr)
