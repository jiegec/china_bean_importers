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
        self.match_keywords = ["微信支付账单明细"]
        self.file_account_name = "wechat"

    def parse_metadata(self, file):
        if m := re.search(r"起始时间：\[([0-9]+-[0-9]+-[0-9]+)", self.full_content):
            self.start = parse(m[1])
        if m := re.search(r"终止时间：\[([0-9]+-[0-9]+-[0-9]+)", self.full_content):
            self.end = parse(m[1])

    def extract(self, file, existing_entries=None):
        entries = []
        begin = False

        for lineno, row in enumerate(csv.reader(self.content)):
            row = [col.strip() for col in row]
            #    0        1        2     3     4     5      6        7       8        9     10
            # 交易时间, 交易类型, 交易对方, 商品, 收/支, 金额, 支付方式, 当前状态, 交易单号, 商户单号, 备注
            if row[0] == "交易时间" and row[1] == "交易类型":
                # skip table header
                begin = True
            elif begin:
                # parse data line
                metadata: dict = data.new_metadata(file.name, lineno)
                tags = set()

                # parse some basic info
                time = parse(row[0])
                units = amount.Amount(D(row[5][1:]), "CNY")
                (
                    _,
                    type,
                    payee,
                    narration,
                    direction,
                    _,
                    method,
                    status,
                    serial,
                    _,
                    note,
                ) = row

                # fill metadata
                metadata["payment_method"] = "微信支付"
                metadata["imported_category"] = type
                metadata["serial"] = serial.strip()
                metadata["time"] = time.time().isoformat()
                if payee == "/":
                    payee = None
                if narration == "/":
                    narration = ""
                if method == "/":
                    method = None
                if "亲属卡交易" in type:
                    tags.add("family-card")

                # workaround
                if direction == "/" and type == "信用卡还款":
                    direction = "支出"
                if direction == "/" and "零钱" in type:
                    direction = "收入"
                    if type == "零钱提现":
                        direction = "支出"
                if (i := narration.find("付款方留言")) != -1:
                    narration = f"{narration[:i]};{narration[i:]}"

                my_assert(
                    direction in ["收入", "支出"],
                    f"Unknown direction: {direction}",
                    lineno,
                    row,
                )
                expense = direction == "支出"

                # determine sign of amount
                if expense:
                    units = -units

                # determine source account
                source_config = self.config["importers"]["wechat"]
                account1 = None
                if method == "零钱" and type == "转入零钱通-来自零钱":
                    # 零钱转入零钱通
                    account1 = source_config["lingqiantong_account"]
                elif method == "零钱通" and type == "零钱通转出-到零钱":
                    # 零钱通转入零钱
                    account1 = source_config["account"]
                elif method == "零钱通" and status.startswith("已退款"):
                    # 零钱通支付退款
                    account1 = source_config["lingqiantong_account"]
                elif method == "零钱通" and status in [
                    "对方已收钱",
                    "已转账"
                ]:
                    # 零钱通转账
                    account1 = source_config["lingqiantong_account"]
                elif method == "零钱通" and type.startswith("零钱通转出-到"):
                    # 零钱通转入卡
                    if tail := match_card_tail(type[len("零钱通转出-到"):]):
                        account1 = find_account_by_card_number(self.config, tail)
                        my_assert(account1, f"Unknown card number {tail}", lineno, row)
                elif method == "零钱" or status in [
                    "已存入零钱",
                    "已到账",
                    "充值完成",
                    "提现已到账",
                ]:  # 微信零钱
                    account1 = source_config["account"]
                elif tail := match_card_tail(method):  # cards
                    account1 = find_account_by_card_number(self.config, tail)
                    my_assert(account1, f"Unknown card number {tail}", lineno, row)

                # TODO: handle 数字人民币 account?
                my_assert(account1, f"Cannot handle source {method}", lineno, row)

                # determine destination account
                account2 = None
                # 1. receive red packet
                if type == "微信红包" and not expense and status == "已存入零钱":
                    account2 = source_config["red_packet_income_account"]
                    narration = "收微信红包"
                # 2. send red packet
                elif expense and "微信红包" in type:
                    narration = "发微信红包"
                    account2 = source_config["red_packet_expense_account"]
                    if payee is not None and payee[0:2] == "发给":
                        payee = payee[2:]
                elif not expense and "微信红包-退款" in type:
                    narration = "发微信红包-退款"
                    account2 = source_config["red_packet_expense_account"]
                # 3. family card
                elif "亲属卡交易" == type:
                    account2 = source_config["family_card_expense_account"]
                elif "亲属卡交易-退款" == type:
                    narration = "亲属卡-退款"
                    account2 = source_config["family_card_expense_account"]
                # 4. group payment
                elif "群收款" == type:
                    narration = "群收款"
                    account2 = (
                        source_config["group_payment_expense_account"]
                        if expense
                        else source_config["group_payment_income_account"]
                    )
                # 5. transfer
                elif "转账" == type:
                    account2 = (
                        source_config["transfer_expense_account"]
                        if expense
                        else source_config["transfer_income_account"]
                    )
                # 6. 微信零钱 related
                elif status in ["充值完成", "提现已到账"]:
                    tail = match_card_tail(method)
                    account2 = find_account_by_card_number(self.config, tail)
                    my_assert(account2, f"Unknown card number {tail}", lineno, row)
                # 7. 零钱通 -> 零钱
                elif method == "零钱" and type == "转入零钱通-来自零钱":
                    account2 = source_config["account"]
                # 8. 零钱 -> 零钱通/卡
                elif method == "零钱通" and type.startswith("零钱通转出-到"):
                    account2 = source_config["lingqiantong_account"]

                # 9. find by narration and payee
                new_account, new_meta, new_tags = match_destination_and_metadata(
                    self.config, narration, payee
                )
                if account2 is None:
                    account2 = new_account
                metadata.update(new_meta)
                tags = tags.union(new_tags)

                # final fallback
                if account2 is None:
                    account2 = unknown_account(self.config, expense)

                # check status
                if (
                    status
                    in ["支付成功", "已存入零钱", "已转账", "对方已收钱", "已收钱"]
                    or "已到账" in status
                ):
                    pass
                elif "退款" in status:
                    tags.add("refund")
                elif status in ["提现失败，已退回零钱", "对方已退还"]:
                    # cancelled
                    my_warn(
                        f"Transaction not successful, please confirm: {status}",
                        lineno,
                        row,
                    )
                    continue
                else:
                    tags.add("confirmation-needed")
                    my_warn(f"Unhandled tx status: {status}", lineno, row)

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
