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
        try:
            with open(file.name, 'r', encoding='utf-8') as f:
                return "csv" in file.name and "微信支付账单明细" in f.readline()
        except:
            return False

    def file_account(self, file):
        return "wechat"

    def file_date(self, file):
        with open(file.name, 'r') as f:
            m = re.search('起始时间：\[([0-9]+-[0-9]+-[0-9]+)', f.read())
            if m:
                date = parse(m[1])
                return date
        return super().file_date(file)

    def file_name(self, file):
        with open(file.name, 'r') as f:
            m = re.search('终止时间：\[([0-9]+-[0-9]+-[0-9]+)', f.read())
            if m:
                date = parse(m[1]).date()
                return f"to.{date}.csv"
        return super().file_name(file)

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False
        with open(file.name, 'r') as f:
            for lineno, row in enumerate(csv.reader(f)):
                #    0        1        2     3     4     5      6        7       8        9     10
                # 交易时间, 交易类型, 交易对方, 商品, 收/支, 金额, 支付方式, 当前状态, 交易单号, 商户单号, 备注
                if row[0] == "交易时间" and row[1] == "交易类型":
                    # skip table header
                    begin = True
                elif begin:
                    # parse data line
                    metadata = data.new_metadata(file.name, lineno)
                    tags = set()

                    # parse some basic info
                    date = parse(row[0]).date()
                    units = amount.Amount(D(row[5][1:]), "CNY")
                    _, type, payee, narration, direction, _, method, status, serial, _, note = row

                    # fill metadata
                    metadata["source"] = "微信支付"
                    metadata["imported_category"] = type
                    metadata["serial"] = serial
                    if payee == '/':
                        payee = None
                    if narration == '/':
                        narration = ''
                    if method == '/':
                        method = None
                    if '亲属卡交易' in type:
                        tags.add('family-card')

                    # workaround
                    if direction == '/' and type == '信用卡还款':
                        direction = '支出'
                    if (i := narration.find('付款方留言')) != -1:
                        narration = f'{narration[:i]};{narration[i:]}'

                    my_assert(direction in [
                              "收入", "支出"], f"Unknown direction: {direction}", lineno, row)
                    expense = direction == "支出"

                    # determine sign of amount
                    if expense:
                        units = -units

                    # determine source account
                    source_config = self.config['source']['wechat']
                    account1 = None
                    if method == '零钱' or status == '已存入零钱':  # 微信零钱
                        account1 = source_config['account']
                    elif tail := match_card_tail(method):  # cards
                        account1 = find_account_by_card_number(
                            self.config, tail)
                        my_assert(
                            account1, f"Unknown card number {tail}", lineno, row)

                    # TODO: handle 零钱通 account
                    # TODO: handle 数字人民币 account?
                    my_assert(
                        account1, f"Cannot handle source {method}", lineno, row)

                    # determine destination account
                    account2 = None
                    # 1. receive red packet
                    if type == "微信红包" and not expense and status == '已存入零钱':
                        account2 = source_config['red_packet_income_account']
                        narration = "收微信红包"
                    # 2. send red packet
                    elif expense and "微信红包" in type:
                        narration = "发微信红包"
                        account2 = source_config['red_packet_expense_account']
                        if payee[0:2] == "发给":
                            payee = payee[2:]
                    # 3. family card
                    elif "亲属卡交易" == type:
                        account2 = source_config['family_card_expense_account']
                    elif "亲属卡交易-退款" == type:
                        narration = "亲属卡-退款"
                        account2 = source_config['family_card_expense_account']
                    # 4. group payment
                    elif "群收款" == type:
                        narration = "群收款"
                        account2 = source_config['group_payment_expense_account'] if expense else source_config['group_payment_income_account']
                    # 5. transfer
                    elif "转账" == type:
                        account2 = source_config['transfer_expense_account'] if expense else source_config['transfer_income_account']
                    # 6. find by narration
                    else:
                        account2 = find_destination_account(
                            self.config, payee, narration, expense)

                    # check status
                    if status in ['支付成功', '已存入零钱', '已转账', '已收钱']:
                        pass
                    elif '退款' in status:
                        tags.add('refund')
                    else:
                        tags.add('confirmation-needed')
                        my_warn(f"Unhandled status: {status}", lineno, row)

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
