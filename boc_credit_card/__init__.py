from dateutil.parser import parse
import datetime
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re
from china_bean_importers.secret import *
import fitz

class Importer(importer.ImporterProtocol):
    def __init__(self) -> None:
        super().__init__()

    def identify(self, file):
        return "PDF" in file.name and "中国银行信用卡" in file.name

    def file_account(self, file):
        return "boc_credit_card"

    def file_date(self, file):
        doc = fitz.open(file.name)
        begin = False
        page = doc[0]
        text = page.get_text("blocks")
        for (x0, y0, x1, y1, content, block_no, block_type) in text:
            content = content.strip()
            if not begin and "Current FCY Total Balance Due" in content:
                begin = True
            elif begin:
                parts = content.split('\n')
                if len(parts) == 4:
                    return parse(parts[1])
                else:
                    break
        return super().file_date(file)

    def extract(self, file, existing_entries=None):
        entries = []
        doc = fitz.open(file.name)
        card_number = None
        begin = False
        lineno = 0
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("blocks")
            for (x0, y0, x1, y1, content, block_no, block_type) in text:
                lineno += 1
                content = content.strip()
                if re.match('(第 [0-9]+ 页/共)|([0-9]+ 页)', content):
                    continue

                if "人民币/RMB" in content:
                    currency = "CNY"
                elif "外币/USD" in content:
                    currency = "USD"
                match = re.search('卡号：([0-9]+)', content)
                if match:
                    card_number = int(match[1])
                    begin = False
                elif card_number:
                    if not begin and "Expenditure" in content:
                        begin = True
                    elif begin and "Loyalty Plan" in content:
                        begin = False
                    elif begin:
                        # Is it a date line?
                        if re.match('[0-9]+-[0-9]+-[0-9]+\n[0-9]+-[0-9]+-[0-9]+\n[0-9]+', content, re.MULTILINE):
                            date = parse(content.split('\n')[0]).date()
                            description = ""
                        else:
                            # Otherwise: Description/Deposit/Expenditure
                            description += content + "\n"
                            done = False
                            if x1 > 500:
                                # Expenditure found
                                done = True
                            elif x1 > 400:
                                # Deposit found
                                done = True
                            if done:
                                payee = None
                                narration = "".join(description.split("\n")[:-2])
                                value = description.split("\n")[-2]
                                units = amount.Amount(D(value), currency)

                                metadata = data.new_metadata(file.name, lineno)
                                account1 = f"Liabilities:Card:BoC:{card_number}"
                                account2 = "Expenses:Unknown"
                                for key in expenses:
                                    if key in narration:
                                        account2 = expenses[key]

                                if x1 > 500:
                                    # Expenditure
                                    units1 = -units
                                else:
                                    # Deposit
                                    units1 = units

                                if "Bank of China Mobile Client" in narration and units1.number > 0:
                                    account2 = f"Assets:Card:BoC:{debit_cards[0]}"


                                txn = data.Transaction(
                                    meta=metadata, date=date, flag=self.FLAG, payee=payee, narration=narration, tags=data.EMPTY_SET, links=data.EMPTY_SET, postings=[
                                        data.Posting(account=account1, units=units1,
                                                    cost=None, price=None, flag=None, meta=None),
                                        data.Posting(account=account2, units=None,
                                                    cost=None, price=None, flag=None, meta=None),
                                    ])
                                entries.append(txn)
        return entries
