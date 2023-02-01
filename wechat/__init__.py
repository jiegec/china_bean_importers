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
        return "csv" in file.name and "微信支付账单明细" in file.head()

    def file_account(self, file):
        return "wechat"

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False
        with open(file.name, 'r') as f:
            for lineno, row in enumerate(csv.reader(f)):
                if row[0] == "交易时间" and row[1] == "交易类型":
                    begin = True
                elif begin:
                    metadata = data.new_metadata(file.name, lineno)
                    date = parse(row[0]).date()
                    units = amount.Amount(D(row[5][1:]), "CNY")
                    payee = row[2]
                    narration = row[3]

                    account1 = "Assets:Unknown"
                    if "中国银行" in row[6]:
                        card_number = int(row[6][5:9])
                        if card_number in debit_cards:
                            account1 = f"Assets:Card:BoC:{card_number}"
                        elif card_number in credit_cards:
                            account1 = f"Liabilities:Card:BoC:{card_number}"
                        else:
                            print(f"Unknown card number: {card_number}")
                            assert False
                    elif "零钱" in row[6] or "零钱" in row[7]:
                        account1 = f"Assets:WeChat"

                    account2 = "Expenses:Unknown"
                    for key in expenses:
                        if key in row[2]:
                            account2 = expenses[key]

                    if "微信红包" in row[1]:
                        narration = row[1]
                        account2 = "Expenses:RedPacket"
                        if payee[0:2] == "发给":
                            payee = payee[2:]
                    elif "亲属卡交易" == row[1]:
                        account2 = "Expenses:Family"
                    elif "亲属卡交易-退款" == row[1]:
                        narration = "亲属卡-退款"
                        account2 = "Expenses:Family"
                    elif "群收款" == row[1]:
                        narration = "群收款"
                        account2 = "Expenses:WeChat:Group"
                    elif "转账" == row[1]:
                        account2 = "Expenses:WeChat:Transfer"

                    # MeiTuan
                    match = re.match('【(.*)】', narration)
                    if match:
                        narration = match[1]

                    if row[4] == "支出":
                        units1 = -units
                    elif row[4] == "收入":
                        units1 = units
                    else:
                        assert False

                    # Remove placeholder
                    if payee == "/":
                        payee = None

                    txn = data.Transaction(
                        meta=metadata, date=date, flag=self.FLAG, payee=payee, narration=narration, tags=data.EMPTY_SET, links=data.EMPTY_SET, postings=[
                            data.Posting(account=account1, units=units1,
                                         cost=None, price=None, flag=None, meta=None),
                            data.Posting(account=account2, units=None,
                                         cost=None, price=None, flag=None, meta=None),
                        ])
                    entries.append(txn)
        return entries
