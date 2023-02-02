from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import re
from china_bean_importers.config import *
from china_bean_importers.common import *
import fitz


def gen_txn(file, parts, lineno, card_number, flag, real_name):
    # Customer Type can be empty
    assert len(parts) == 6 or len(parts) == 7

    # parts[5]: 对手信息
    payee = parts[5]
    if len(parts) == 7:
        # parts[6]: 客户摘要
        narration = parts[6]
    else:
        # parts[4]: 交易摘要
        narration = parts[4]
    # parts[0]: 记账日期
    date = parse(parts[0]).date()
    # parts[2]: 金额
    units1 = amount.Amount(D(parts[2]), "CNY")

    metadata = data.new_metadata(file.name, lineno)
    account1 = f"Assets:Card:CMB:{card_number}"
    account2 = "Expenses:Unknown"
    for key in expenses:
        if key in narration:
            account2 = expenses[key]

    # Handle transfer to credit/debit cards
    # parts[5]: 对手信息
    if parts[5].startswith(real_name):
        card_number2 = int(parts[5][-4:])
        new_account = find_account_by_card_number(card_number2)
        if new_account is not None:
            account2 = new_account

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
        if "pdf" in file.name:
            doc = fitz.open(file.name)
            if doc.is_encrypted:
                return False
            if "招商银行交易流水" in doc[0].get_text("text"):
                return True
        return False

    def file_account(self, file):
        return "cmb_debit_card"

    def extract(self, file, existing_entries=None):
        entries = []
        doc = fitz.open(file.name)
        card_number = None
        begin = False
        lineno = 0
        real_name = None
        for i in range(doc.page_count):
            parts = []
            page = doc[i]
            text = page.get_text("words")
            last_y0 = 0
            last_content = ""
            # y position of columns
            columns = [30, 50, 100, 200, 280, 350, 450]
            for (x0, y0, x1, y1, content, block_no, line_no, word_no) in text:
                # print(x0, y0, x1, y1, repr(content), block_no, line_no, word_no)
                lineno += 1
                content = content.strip()

                # Find real name
                match = re.search('名：(.*)', content)
                if match:
                    real_name = match[1]

                match = re.search('[0-9]{16}', content)
                if match and card_number is None:
                    card_number = int(match[0][-4:])
                    begin = False
                elif card_number:
                    if not begin and "Type" in content and "Customer" in last_content:
                        begin = True
                    elif begin and "合并统计" in content:
                        begin = False
                    elif begin:
                        if x0 < 50:
                            # a new entry
                            if len(parts) > 0:
                                txn = gen_txn(file, parts, lineno,
                                              card_number, self.FLAG, real_name)
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
                last_content = content
            if len(parts) > 0:
                txn = gen_txn(file, parts, lineno,
                              card_number, self.FLAG, real_name)
                entries.append(txn)
                parts = []
        return entries
