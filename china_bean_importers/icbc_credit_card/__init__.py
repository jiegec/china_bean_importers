from beancount.core.number import D
from beancount.core import data, amount
from beancount.ingest import importer
from dateutil.parser import parse
import re

from china_bean_importers.common import *

REGEX_YYYY_MM_DD = re.compile(r"(\d+)年(\d+)月(\d+)日")

# Symbols
C_CARD_NUMBER = "card_number"
C_DATE = "date"
C_TYPE = "type"
C_MERCHANT = "merchant"
C_TXN = "txn_amount"
C_DST = "dst_amount"

# Constants
COLUMN_NAMES = {
    "卡号后四位": C_CARD_NUMBER,
    "交易日": C_DATE,
    "交易类型": C_TYPE,
    "商户名称/城市": C_MERCHANT,
    "交易金额/币种": C_TXN,
    "记账金额/币种": C_DST
}
EMAIL_KEYWORD = "中国工商银行客户对账单"

REQUIRED_FIELDS = {C_CARD_NUMBER, C_DATE, C_MERCHANT, C_DST}


def check_required_fields(obj: dict, required_fields: set[str]) -> bool:
    """
    Check whether required fields are present in a dict.
    """
    keys = obj.keys()
    for i in required_fields:
        if i not in keys:
            return False
    return True


def to_txn_object(values: list[str], header_index: dict[str, int]) -> dict[str, str]:
    """
    Populate a Txn dict given an array of values and corresponding list index
    for each field.
    """
    ret = {}
    for [field_id, index] in header_index.items():
        if len(values) > index:
            ret[field_id] = values[index]
    return ret


class Importer(importer.ImporterProtocol):

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self.match_keywords = [EMAIL_KEYWORD]

    def identify(self, file):
        if file.name.upper().endswith(".EML"):
            self.type = "email"

            from bs4 import BeautifulSoup
            from email import policy
            from email.parser import Parser
            import quopri

            with open(file.name, "r", encoding="utf-8") as f:
                raw_email = Parser(policy=policy.default).parse(
                    f)
                raw_body_html = quopri.decodestring(
                    raw_email.get_body().get_payload())
                self.body = BeautifulSoup(raw_body_html, features="lxml")
                for i in self.body.find_all("td"):
                    if "对账单生成日" in (i.string or ""):
                        [y, m, d] = REGEX_YYYY_MM_DD.search(
                            i.string).groups()
                        self.stmt_date = parse(f"{y}-{m}-{d}")
                is_workable = EMAIL_KEYWORD in raw_email["Subject"]
                return is_workable
        return False

    def file_account(self, file):
        return "icbc_credit_card"

    def file_date(self, file):
        if self.type == "email":
            return self.stmt_date
        return super().file_date(file)

    # common methods for table-based import
    def extract(self, file, existing_entries=None):
        return list(self.process_outer(self.body, file.name))

    def process_inner(self, table, file_name):
        headers_processed = False
        header_index: dict[str, int] = {}
        lineno = 0

        for i in table.find_all("tr", recursive=False):
            lineno += 1
            # Header processing
            if not headers_processed:
                headers = list(
                    map(lambda x: x.string.strip(), i.find_all("td")))
                for [field_name, field_id] in COLUMN_NAMES.items():
                    if field_name in headers:
                        header_index[field_id] = headers.index(field_name)
                print(f"Discovered fields: {header_index}", file=sys.stderr)
                if not check_required_fields(header_index, REQUIRED_FIELDS):
                    print(
                        "No enough information is provided in the header, skipping the table", file=sys.stderr)
                    return
                headers_processed = True
                continue

            # Data processing
            values: list[str] = list(
                map(lambda x: x.string.strip(), i.find_all("td")))
            txn_object = to_txn_object(values, header_index)
            if not check_required_fields(txn_object, REQUIRED_FIELDS):
                print(f"Skipping line {values}", file=sys.stderr)
                continue
            beancount_txn = self.to_beancount_txn(
                txn_object, file_name, lineno)
            if beancount_txn is not None:
                yield beancount_txn

    def process_outer(self, soup, file_name):
        ret = []
        for i in soup.find_all("table"):
            # try:
            is_txns = False
            tr_items = i.find("tr", recursive=False)
            if tr_items is None:
                continue
            for j in tr_items.find_all("td", recursive=False):
                if j.string == "交易日":
                    is_txns = True
                    break
            if is_txns:
                yield from self.process_inner(i, file_name)
            # except Exception:
            #     pass

    def to_beancount_txn(self, txn_object, file_name, lineno):
        is_expense = False
        dst_amount = txn_object[C_DST]
        if dst_amount.endswith("(支出)"):
            is_expense = True
            dst_amount = dst_amount.rstrip("(支出)")
        elif dst_amount.endswith("(存入)"):
            is_expense = False
            dst_amount = dst_amount.rstrip("(存入)")
        else:
            print("Unknown transaction direction, skipping", file=sys.stderr)
            return None
        [dst_number, dst_currency] = dst_amount.split("/")

        metadata = data.new_metadata(file_name, lineno)
        txn_units = None
        if C_TXN in txn_object:
            original_amount = txn_object[C_TXN]
            [txn_number, txn_currency] = original_amount.split("/")
            if dst_currency != txn_currency:
                metadata["original_amount"] = f"{txn_number} {txn_currency}"
                # TODO: It can fill per-unit price (@) but usually people may want total price (@@)
                txn_units = amount.Amount(D(txn_number), txn_currency)

        date = parse(txn_object[C_DATE]).date()

        card_number = txn_object[C_CARD_NUMBER]
        account1 = find_account_by_card_number(self.config, card_number)

        payee = txn_object.get(C_MERCHANT) or "Unknown"
        narration = txn_object.get(C_TYPE) or None
        tags = set()

        if "退款" in narration:
            tags.add("refund")

        units = amount.Amount(D(dst_number), dst_currency)
        if is_expense:
            units = -units

        if m := match_destination_and_metadata(self.config, narration, payee):
            (account2, new_meta, new_tags) = m
            metadata.update(new_meta)
            tags = tags.union(new_tags)
        if account2 is None:
            account2 = unknown_account(self.config, units.number < 0)

        return data.Transaction(
            meta=metadata,
            date=date,
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
                    price=txn_units,
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
