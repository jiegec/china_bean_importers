from dateutil.parser import parse
from beancount.core import data, amount
from beancount.core.number import D
import re

from china_bean_importers.common import *
from china_bean_importers.importer import PdfImporter


def gen_txn(config, file, parts, lineno, flag, card_acc):
    # my_assert(len(parts) >= 10 or len(parts) == 5, f'Cannot parse line in PDF', lineno, parts)
    #    0       1       2       3      4        5        6      7        8         9           10
    # 凭证类型, 凭证号码, 交易时间, 摘要, 交易金额, 账户余额, 现转标志, 交易渠道, 交易机构, 对方户名/账号, 对方行名
    # either 11/10 items, or only [2:6] is contained

    # fill to 11 fields
    if parts[0][:2] == "20":
        parts = [""] * 2 + parts
    parts = parts + [""] * (11 - len(parts))

    if "/" in parts[9]:
        payee, payee_account = parts[9].split("/")
    else:
        payee, payee_account = parts[9], ""
    narration = parts[3]
    full_time = parse(parts[2])
    date = full_time.date()
    units1 = amount.Amount(D(parts[4]), "CNY")

    # check blacklist
    if in_blacklist(config, narration):
        print(
            f"Item in blacklist: {date} {narration} [{units1}]",
            file=sys.stderr,
            end=" -- ",
        )
        if units1 < amount.Amount(D(0), "CNY"):
            print(f"Expense skipped", file=sys.stderr)
            return None
        else:
            print(f"Income kept in record", file=sys.stderr)

    metadata = data.new_metadata(file.name, lineno)
    metadata["time"] = full_time.time().isoformat()
    if parts[7] != "":
        metadata["source"] = parts[7]
    if payee_account != "":
        metadata["payee_account"] = payee_account
    if parts[10] != "":
        metadata["payee_branch"] = parts[10]

    tags = set()

    if m := match_destination_and_metadata(config, narration, payee):
        (account2, new_meta, new_tags) = m
        metadata.update(new_meta)
        tags = tags.union(new_tags)
    if account2 is None:
        account2 = unknown_account(config, units1.number < 0)

    # try to find transfer destination account
    if parts[9] != "":
        card_number2 = parts[9][-4:]
        new_account = find_account_by_card_number(config, card_number2)
        if new_account is not None:
            account2 = new_account

    if "退款" in parts[5]:
        tags.add("refund")

    txn = data.Transaction(
        meta=metadata,
        date=date,
        flag=flag,
        payee=payee,
        narration=narration,
        tags=tags,
        links=data.EMPTY_SET,
        postings=[
            data.Posting(
                account=card_acc,
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
    return txn


class Importer(PdfImporter):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.match_keywords = ["民生银行", "个人账户对账单"]
        self.file_account_name = "cmbc_debit_card"
        self.column_offsets = [22, 56, 97, 173, 335, 413, 448, 482, 533, 568, 696]
        self.content_start_keyword = "对方行名"
        self.content_end_keyword = "______________"

    def parse_metadata(self, file):
        match = re.search(
            r"起止日期:([0-9]{4}\/[0-9]{2}\/[0-9]{2}).*([0-9]{4}\/[0-9]{2}\/[0-9]{2})",
            self.full_content,
        )
        assert match
        self.start = parse(match[1])
        self.end = parse(match[2])

        match = re.search(r"客户姓名:(\w+)", self.full_content)
        assert match
        self.real_name = match[1]

        match = re.search(r"客户账号:([0-9]+)", self.full_content)
        assert match
        card_number = match[1]
        self.card_acc = find_account_by_card_number(self.config, card_number[-4:])
        my_assert(self.card_acc, f"Unknown card number {card_number}", 0, 0)

    def generate_tx(self, row, lineno, file):
        return gen_txn(self.config, file, row, lineno, self.FLAG, self.card_acc)
