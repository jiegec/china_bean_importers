from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re
from china_bean_importers.secret import *


class Importer(importer.ImporterProtocol):
    def __init__(self) -> None:
        super().__init__()

    def identify(self, file):
        return "csv" in file.name and "电子客户回单" in file.head()

    def file_account(self, file):
        return "alipay_mobile"

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False
        with open(file.name, 'r', encoding='gbk') as f:
            for lineno, row in enumerate(csv.reader(f)):
                row = [col.strip() for col in row]
                if row[0] == "收/支" and row[1] == "交易对方":
                    begin = True
                elif begin and row[0].startswith('------'):
                    break
                elif begin:
                    metadata = data.new_metadata(file.name, lineno)
                    date = parse(row[10]).date()
                    units = amount.Amount(D(row[5]), "CNY")
                    payee = row[1]
                    narration = row[3]

                    account1 = "Assets:Alipay"
                    if row[4] == "花呗":
                        account1 = "Liabilities:Alipay:HuaBei"
                    elif row[4].startswith("中国银行储蓄卡"):
                        card_number = int(row[4][8:12])
                        if card_number in debit_cards:
                            account1 = f"Assets:Card:BoC:{card_number}"
                        else:
                            print(f"Unknown card number: {card_number}")
                            assert False
                    elif row[4].startswith("中国银行信用卡"):
                        card_number = int(row[4][8:12])
                        if card_number in credit_cards:
                            account1 = f"Liabilities:Card:BoC:{card_number}"
                        else:
                            print(f"Unknown card number: {card_number}")
                            assert False

                    account2 = "Expenses:Unknown"
                    for key in expenses:
                        if key in row[1]:
                            account2 = expenses[key]

                    if row[0] == "支出":
                        units1 = -units
                    elif row[0] == "收入" or row[0] == "其他":
                        units1 = units
                    else:
                        assert False

                    if row[1] == "花呗":
                        account2 = "Liabilities:Alipay:HuaBei"
                        units1 = -units

                    txn = data.Transaction(
                        meta=metadata, date=date, flag=self.FLAG, payee=payee, narration=narration, tags=data.EMPTY_SET, links=data.EMPTY_SET, postings=[
                            data.Posting(account=account1, units=units1,
                                         cost=None, price=None, flag=None, meta=None),
                            data.Posting(account=account2, units=None,
                                         cost=None, price=None, flag=None, meta=None),
                        ])
                    entries.append(txn)
        return entries
