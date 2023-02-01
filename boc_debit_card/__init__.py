from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import re
from china_bean_importers.secret import *
import fitz


def gen_txn(file, parts, lineno, card_number, flag):
    # print(parts)
    assert len(parts) == 12

    payee = parts[9]
    narration = parts[8]
    if '------' in narration:
        narration = parts[5]
    date = parse(parts[0]).date()
    units1 = amount.Amount(D(parts[3]), "CNY")

    metadata = data.new_metadata(file.name, lineno)
    account1 = f"Assets:Card:BoC:{card_number}"
    account2 = "Expenses:Unknown"
    for key in expenses:
        if key in narration:
            account2 = expenses[key]

    txn = data.Transaction(
        meta=metadata, date=date, flag=flag, payee=payee, narration=narration, tags=data.EMPTY_SET, links=data.EMPTY_SET, postings=[
            data.Posting(account=account1, units=units1,
                         cost=None, price=None, flag=None, meta=None),
            data.Posting(account=account2, units=None,
                         cost=None, price=None, flag=None, meta=None),
        ])
    return txn


class Importer(importer.ImporterProtocol):
    def __init__(self) -> None:
        super().__init__()

    def identify(self, file):
        return "pdf" in file.name

    def file_account(self, file):
        return "boc_debit_card"

    def file_date(self, file):
        doc = fitz.open(file.name)
        if doc.is_encrypted:
            for password in pdf_passwords:
                doc.authenticate(password)
        page = doc[0]
        text = page.get_text("blocks")
        for (x0, y0, x1, y1, content, block_no, block_type) in text:
            match = re.match(
                '交易区间： ([0-9]+-[0-9]+-[0-9]+) 至 ([0-9]+-[0-9]+-[0-9]+)', content)
            if match:
                return parse(match[1])
        return super().file_date(file)

    def file_name(self, file):
        doc = fitz.open(file.name)
        if doc.is_encrypted:
            for password in pdf_passwords:
                doc.authenticate(password)
        page = doc[0]
        text = page.get_text("blocks")
        for (x0, y0, x1, y1, content, block_no, block_type) in text:
            match = re.match(
                '交易区间： ([0-9]+-[0-9]+-[0-9]+) 至 ([0-9]+-[0-9]+-[0-9]+)', content)
            if match:
                return match[2] + ".pdf"
        return super().file_name(file)

    def extract(self, file, existing_entries=None):
        entries = []
        doc = fitz.open(file.name)
        if doc.is_encrypted:
            for password in pdf_passwords:
                doc.authenticate(password)
        card_number = None
        begin = False
        lineno = 0
        for i in range(doc.page_count):
            parts = []
            page = doc[i]
            text = page.get_text("words")
            last_y0 = 0
            # y position of columns
            columns = [46, 112, 172, 234, 300,
                       339, 405, 447, 518, 590, 660, 740]
            for (x0, y0, x1, y1, content, block_no, line_no, word_no) in text:
                # print(x0, y0, x1, y1, repr(content), block_no, line_no, word_no)
                lineno += 1
                content = content.strip()

                match = re.search('[0-9]{19}', content)
                if match and card_number is None:
                    card_number = int(match[0][-4:])
                    begin = False
                elif card_number:
                    if not begin and "对方开户行" in content:
                        begin = True
                    elif begin and "温馨提示" in content:
                        begin = False
                    elif begin:
                        if x0 < 50:
                            # a new entry
                            if len(parts) > 0:
                                txn = gen_txn(file, parts, lineno,
                                              card_number, self.FLAG)
                                entries.append(txn)
                                parts = []

                            # date
                            parts.append(content)
                        else:
                            if len(parts) < len(columns) and x0 >= columns[len(parts)]:
                                # new column
                                parts.append(content)
                            else:
                                # same column
                                if y0 == last_y0:
                                    # no newline
                                    parts[-1] = parts[-1] + " " + content
                                else:
                                    # newline
                                    parts[-1] = parts[-1] + content
                        last_y0 = y0
            if len(parts) > 0:
                txn = gen_txn(file, parts, lineno,
                              card_number, self.FLAG)
                entries.append(txn)
                parts = []
        return entries
