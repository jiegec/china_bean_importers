from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re

from china_bean_importers.common import *


class Importer(importer.ImporterProtocol):
    def __init__(self, config) -> None:
        super().__init__()
        self.config = config

    def identify(self, file):
        return "txt" in file.name and "支付宝交易记录明细查询" in file.head()

    def file_account(self, file):
        return "alipay_web"

    def file_date(self, file):
        with open(file.name, "r", encoding="gbk") as f:
            for row in csv.reader(f):
                m = re.search(r"起始日期:\[([0-9 :-]+)\]", row[0])
                if m:
                    date = parse(m[1])
                    return date
        return super().file_date(file)

    def file_name(self, file):
        with open(file.name, "r", encoding="gbk") as f:
            for row in csv.reader(f):
                m = re.search(r"终止日期:\[([0-9 :-]+)\]", row[0])
                if m:
                    date = parse(m[1])
                    return "to." + date.date().isoformat() + ".txt"
        return super().file_name(file)

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False
        with open(file.name, "r", encoding="gbk") as f:
            for lineno, row in enumerate(csv.reader(f)):
                row = [col.strip() for col in row]
                if row[0] == "交易号" and row[1] == "商家订单号":
                    begin = True
                elif begin and row[0].startswith("------"):
                    break
                elif begin:
                    metadata = data.new_metadata(file.name, lineno)
                    date = parse(row[2]).date()
                    units = amount.Amount(D(row[9]), "CNY")
                    payee = row[7]
                    narration = row[8]

                    account1 = "Assets:Alipay"
                    account2 = find_destination_account(
                        self.config, payee, narration, row[10] == "支出"
                    )

                    if row[10] == "支出":
                        units1 = -units
                    elif row[10] == "收入" or row[10] == "其他":
                        units1 = units
                    else:
                        assert False

                    txn = data.Transaction(
                        meta=metadata,
                        date=date,
                        flag=self.FLAG,
                        payee=payee,
                        narration=narration,
                        tags=data.EMPTY_SET,
                        links=data.EMPTY_SET,
                        postings=[
                            data.Posting(
                                account=account1,
                                units=units1,
                                cost=None,
                                price=None,
                                flag=None,
                                meta=None,
                            ),
                            data.Posting(
                                account=account2,
                                units=None,
                                cost=None,
                                price=None,
                                flag=None,
                                meta=None,
                            ),
                        ],
                    )
                    entries.append(txn)
        return entries
