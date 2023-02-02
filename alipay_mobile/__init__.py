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
        with open(file.name, 'r', encoding='gbk') as f:
            return "csv" in file.name and "电子客户回单" in f.readline()
        

    def file_account(self, file):
        return "alipay_mobile"

    def file_date(self, file):
        with open(file.name, 'r', encoding='gbk') as f:
            for row in csv.reader(f):
                m = re.search('起始时间：\[([0-9 :-]+)\]', row[0])
                if m:
                    date = parse(m[1])
                    return date
        return super().file_date(file)

    def file_name(self, file):
        with open(file.name, 'r', encoding='gbk') as f:
            for row in csv.reader(f):
                m = re.search('终止时间：\[([0-9 :-]+)\]', row[0])
                if m:
                    date = parse(m[1])
                    return "to." + date.date().isoformat() + '.csv'
        return super().file_name(file)

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False
        with open(file.name, 'r', encoding='gbk') as f:
            for lineno, row in enumerate(csv.reader(f)):
                row = [col.strip() for col in row]
                #   0      1        2        3        4       5      6        7        8          9       10
                # 收/支, 交易对方, 对方账号, 商品说明, 收付款方式, 金额, 交易状态, 交易分类, 交易订单号, 商家订单号, 交易时间
                if row[0] == "收/支" and row[1] == "交易对方":
                    # skip table header
                    begin = True
                elif begin and row[0].startswith('------'):
                    # end of data
                    break
                elif begin:
                    # parse data line
                    metadata = data.new_metadata(file.name, lineno)
                    tags = set()

                    # parse some basic info
                    date = parse(row[10]).date()
                    units = amount.Amount(D(row[5]), "CNY")
                    metadata["serial"] = row[8]
                    direction, payee, payee_account, narration, method, _, status, category = row[:8]

                    # fill metadata
                    if payee_account != '':
                        metadata["payee_account"] = row[2]
                    metadata["imported_category"] = category

                    expense = None
                    # determine direction
                    if direction == '支出':
                        expense = True
                    elif direction == '收入':
                        expense = False
                    elif direction == '其他':
                        if '退款' in narration or '退款成功' in status:
                            expense = False
                            tags.add('refund')
                        if method == '余额宝' and '收益' in narration:
                            expense = False
                        if payee == '余额宝' and '转入' in narration:
                            expense = True
                        if method == '花呗':
                            if '还款' in narration:
                                expense = True
                    
                    my_assert(expense is not None, f"Unknown transaction type", lineno, row)
                    
                    # determine sign of amount
                    if expense:
                        units = -units

                    # find source from 收付款方式
                    alipay_config = self.config['source']['alipay']
                    account1 = alipay_config['account'] # 支付宝余额
                    if method == "花呗":
                        account1 = alipay_config['huabei_account']
                    if method == "余额宝":
                        account1 = alipay_config['yuebao_account']
                    elif tail := match_card_tail(method):
                        account1 = find_account_by_card_number(self.config, tail)
                        my_assert(account1, f"Unknown card number {tail}", lineno, row)

                    # find destination from 商品说明
                    account2 = find_destination_account(self.config, narration, expense)

                    # find from 交易对方

                    # check status and add warning if needed
                    if '成功' not in status:
                        my_warn(f"Transaction not successful, please confirm", lineno, row)
                        tags.add('confirmation-needed')

                    # create transaction
                    txn = data.Transaction(
                        meta=metadata, date=date, flag=self.FLAG, payee=payee, narration=narration, tags=tags, links=data.EMPTY_SET, postings=[
                            data.Posting(account=account1, units=units,
                                         cost=None, price=None, flag=None, meta=None),
                            data.Posting(account=account2, units=None,
                                         cost=None, price=None, flag=None, meta=None),
                        ])
                    entries.append(txn)

        return entries
