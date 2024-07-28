from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import csv
import re

from china_bean_importers.common import *
from china_bean_importers.importer import CsvImporter


class Importer(CsvImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.encoding = "gbk"
        self.match_keywords = ["支付宝", "电子客户回单"]
        self.file_account_name = "alipay_mobile"

    def parse_metadata(self, file):
        if m := re.search(r"起始时间：\[([0-9 :-]+)\]", self.full_content):
            self.start = parse(m[1])
        if m := re.search(r"终止时间：\[([0-9 :-]+)\]", self.full_content):
            self.end = parse(m[1])

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False

        for lineno, row in enumerate(csv.reader(self.content)):
            row = [col.strip() for col in row]
            if len(row) <= 12:
                continue
            #   0        1        2        3       4       5     6       7        8          9       10      11
            # 交易时间, 交易分类, 交易对方, 对方账号, 商品说明, 收/支, 金额, 收付款方式, 交易状态, 交易订单号, 商家订单号, 备注

            if row[0] == "交易时间" and row[1] == "交易分类":
                # skip table header
                begin = True
            elif begin and row[0].startswith("------"):
                # end of data
                break
            elif begin:
                # parse data line
                metadata: dict = data.new_metadata(file.name, lineno)
                tags = set()

                # parse some basic info
                (
                    time,
                    category,
                    payee,
                    payee_account,
                    narration,
                    direction,
                    amt,
                    method,
                    status,
                    serial,
                ) = row[:10]
                time = parse(time)
                units = amount.Amount(D(amt), "CNY")
                metadata["serial"] = serial

                # fill metadata
                if payee_account != "":
                    metadata["payee_account"] = payee_account
                metadata["imported_category"] = category
                metadata["payment_method"] = "支付宝"
                metadata["time"] = time.time().isoformat()
                if category == "亲友代付" or "亲情卡" in narration:
                    tags.add("family-card")

                expense = None
                # determine direction
                if direction == "支出":
                    expense = True
                elif direction == "收入":
                    expense = False
                elif direction == "其他" or direction == "不计收支":
                    if "退款" in narration or "退款成功" in status:
                        expense = False
                        tags.add("refund")
                    if method == "余额宝" and "收益" in narration:
                        expense = False
                    if payee == "余额宝" and "转入" in narration:
                        expense = True
                    if method == "花呗":
                        if "还款" in narration:
                            expense = True
                    if payee == "花呗" and "还款" in narration:
                        expense = True
                    if expense is None:
                        # if '交易关闭' in status or '解冻成功' in status:
                        my_warn(
                            f"Transaction type not recognized, please confirm",
                            lineno,
                            row,
                        )
                        expense = True
                        tags.add("confirmation-needed")

                my_assert(expense is not None, f"Unknown transaction type", lineno, row)

                # determine sign of amount
                if expense:
                    units = -units

                # find source from 收付款方式
                # TODO: handle 红包 & 余额宝转入
                source_config = self.config["importers"]["alipay"]
                account1 = source_config["account"]  # 支付宝余额
                if "花呗" in method: # Handle discount transactions like "花呗&红包"
                    account1 = source_config["huabei_account"]
                if method == "余额宝":
                    account1 = source_config["yuebao_account"]
                elif tail := match_card_tail(method):
                    account1 = find_account_by_card_number(self.config, tail)
                    my_assert(account1, f"Unknown card number {tail}", lineno, row)

                # find from 商品说明 and 交易对方
                account2 = None
                if payee == "余额宝" and "自动转入" in narration:
                    account2 = source_config["yuebao_account"]
                elif category == "转账红包":
                    account2 = (
                        source_config["red_packet_income_account"]
                        if not expense
                        else source_config["red_packet_expense_account"]
                    )
                elif expense and category == "信用借还":
                    if "还款" in narration and "花呗" in payee:
                        account2 = source_config["huabei_account"]
                    elif "抖音月付" in narration:
                        account2 = source_config["douyin_monthly_payment_account"]
                else:
                    new_account, new_meta, new_tags = match_destination_and_metadata(
                        self.config, narration, payee
                    )
                    if new_account:
                        account2 = new_account
                    metadata.update(new_meta)
                    tags = tags.union(new_tags)
                # then try category
                if account2 is None:
                    if category in source_config["category_mapping"]:
                        account2 = source_config["category_mapping"][category]
                    else:
                        account2 = unknown_account(self.config, expense)

                if "&" in method:
                    my_warn(
                        f"Multiple payment methods found, please confirm", lineno, row
                    )
                    tags.add("confirmation-needed")

                # check status and add warning if needed
                if "成功" not in status:
                    my_warn(f"Transaction not successful, please confirm", lineno, row)
                    tags.add("confirmation-needed")

                # create transaction
                txn = data.Transaction(
                    meta=metadata,
                    date=time.date(),
                    flag=self.FLAG,
                    payee=payee,
                    narration=narration,
                    tags=tags,
                    links=data.EMPTY_SET,
                    postings=[
                        data.Posting(
                            account=account1,
                            units=units,
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
