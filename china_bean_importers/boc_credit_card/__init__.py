from dateutil.parser import parse
from beancount.ingest import importer
from beancount.core import data, amount
from beancount.core.number import D

import re
import sys

from china_bean_importers.common import *


class Importer(importer.ImporterProtocol):
    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self.rate = None

    def get_config(self, cfg, account, narration):
        if "importers" not in self.config:
            return None
        if "boc" not in self.config["importers"]:
            return None
        if "credit" not in self.config["importers"]["boc"]:
            return None
        if cfg not in self.config["importers"]["boc"]["credit"]:
            return None

        if callable(self.config["importers"]["boc"]["credit"][cfg]):
            return self.config["importers"]["boc"]["credit"][cfg](account, narration)
        return self.config["importers"]["boc"]["credit"][cfg]

    def repayment_tag(self, account, narration) -> str:
        return self.get_config("repayment_tag", account, narration)

    def extract_repayment_rate(self, account, narration) -> bool:
        return self.get_config("extract_repayment_rate", account, narration)

    def identify(self, file):
        if file.name.upper().endswith(".PDF"):
            self.type = "pdf"

            import fitz
            if "中国银行信用卡" in file.name:
                self.doc = fitz.open(file.name)
                return True
            elif "中国银行" in file.name:
                doc = fitz.open(file.name)
                if "信用卡账单" in doc[0].get_text():
                    self.doc = doc
                    return True
            return False
        elif file.name.upper().endswith(".EML"):
            self.type = "email"
            from bs4 import BeautifulSoup
            import email
            from email import policy
            import quopri

            try:
                raw_email = email.message_from_file(
                    open(file.name), policy=policy.default
                )
                raw_body_html = quopri.decodestring(
                    raw_email.get_body().get_payload()
                ).decode()
                self.body = BeautifulSoup(raw_body_html, features="lxml")
                return self.body.title.text == "中国银行电子帐单"
            except BaseException:
                return False

    def file_account(self, file):
        return "boc_credit_card"

    def file_date(self, file):
        if self.type == "pdf":
            begin = False
            page = self.doc[0]
            text = page.get_text("blocks")
            for x0, y0, x1, y1, content, block_no, block_type in text:
                content = content.strip()
                if not begin and "Current FCY Total Balance Due" in content:
                    begin = True
                elif begin:
                    parts = content.split("\n")
                    if len(parts) == 4:
                        return parse(parts[1])
                    elif len(parts) == 3 or len(parts) == 2:
                        return parse(parts[0])
                    else:
                        break
        elif self.type == "email":
            info_table = self.body.select("table.bill_sum_detail_table")[0]
            # 到期还款日 账单日 本期人民币欠款总计 本期外币欠款总计
            bill_date = info_table.find_all("td")[1].text
            return parse(bill_date)
        return super().file_date(file)

    def extract_text_entries(self):
        card_num_regex = re.compile(r".*\(卡号(:|：)(\d+)\)")
        currency_regex = re.compile(r".*(\(([a-zA-Z]+)\))(\w+)?交易明细.*", flags=re.DOTALL)

        # collect text entries from EML / PDF
        # 货币 交易日 银行记账日 卡号后四位 交易描述 存入 支出
        text_entries = []
        ref_rate = None

        if self.type == "pdf":
            card_number = None
            begin = False
            lineno = 0

            for i in range(self.doc.page_count):
                page = self.doc[i]
                text = page.get_text("blocks")
                for x0, y0, x1, y1, content, block_no, block_type in text:
                    lineno += 1
                    content = content.strip()
                    if block_type != 0:  # 0: text, 1: image
                        continue
                    if re.match(r"(第 [0-9]+ 页/共)|([0-9]+ 页)", content):
                        continue

                    if m := re.match(r"参考汇率: *([0-9.]+)", content):
                        rate = float(m.group(1))
                        if rate == 0:
                            rate = None
                        elif rate > 100:
                            rate = rate / 100

                        if rate is not None:
                            self.rate = rate

                    if "人民币交易明细" in content:
                        currency = "CNY"
                    elif m := currency_regex.match(content):
                        currency = m.group(2)
                    match = card_num_regex.search(content)
                    if match:
                        card_number = match[2][-4:]
                        begin = False
                    elif card_number:
                        if not begin and "Expenditure" in content:
                            begin = True
                        elif begin and (
                            "Loyalty Plan" in content or "交易日" in content
                        ):
                            begin = False
                        elif begin:
                            # Match date part first
                            # card number can be empty
                            m = re.match(
                                r"[0-9]+-[0-9]+-[0-9]+\n[0-9]+-[0-9]+-[0-9]+(\n[0-9]+)?",
                                content,
                                re.MULTILINE,
                            )
                            if m:
                                lines = content.split("\n")
                                trans_date = lines[0]
                                post_date = lines[1]
                                description = ""
                                # After date part matched, continue to match the rest
                                content = content[m.end() :]

                            # Description/Deposit/Expenditure
                            description += content + "\n"
                            done = False
                            if x1 > 500:
                                # Expenditure found
                                expense = True
                                done = True
                            elif x1 > 400:
                                # Deposit found
                                expense = False
                                done = True
                            if done:
                                desc_lines = description.split("\n")
                                orig_narration = "".join(desc_lines[:-2])
                                value = desc_lines[-2]
                                entry = [
                                    currency,
                                    trans_date,
                                    post_date,
                                    card_number,
                                    orig_narration,
                                    value if not expense else "",
                                    value if expense else "",
                                ]
                                text_entries.append(entry)

        elif self.type == "email":
            for lineno, card in enumerate(self.body.select("div.bill_card_detail")):
                card_num = None
                currency = None

                for tag in card.children:
                    import bs4.element

                    if not isinstance(tag, bs4.element.Tag):
                        continue

                    if tag.name == "div" and "bill_card_des" in tag["class"]:
                        after_currency = False
                        text = tag.text.strip()

                        if m := card_num_regex.match(text):
                            if card_num is None or card_num == m.group(1):
                                card_num = m.group(1)
                            else:
                                my_warn(
                                    f"Card number mismatch: old {card_num} vs new {m.group(1)}",
                                    lineno,
                                    None,
                                )

                        if "人民币交易明细" in text:
                            after_currency = True
                            currency = "CNY"
                        elif m := currency_regex.match(text):
                            after_currency = True
                            if m.group(3) == "人民币":
                                currency = "CNY"
                            elif m.group(3) == "外币":
                                currency = m.group(2)

                    if tag.name == "table" and after_currency:
                        curr_card_enries = []
                        for row in tag.findAll("tr")[1:]:
                            cols = list(
                                map(lambda t: t.text.strip(), row.findAll("td"))
                            )
                            cols = [currency] + cols
                            curr_card_enries.append(cols)
                        if len(curr_card_enries) > 0:
                            text_entries.extend(curr_card_enries)
                        else:
                            my_warn(f"Empty entries for {card_num}", 0, None)

        return text_entries

    def extract(self, file, existing_entries=None):

        # generate beancount posting entries
        entries = []

        last_account = None
        for lineno, entry in enumerate(self.extract_text_entries()):
            # print(entry, file=sys.stderr)
            # 货币 交易日 银行记账日 卡号后四位 交易描述 存入 支出
            (
                currency,
                trans_date,
                post_date,
                card_number,
                orig_narration,
                deposit,
                expense,
            ) = entry

            value = deposit if deposit != "" else expense
            if value == "":
                my_warn(f"Empty value for entry", lineno, entry)
                continue

            units = amount.Amount(D(value), currency)

            if "-" in orig_narration:
                hypen_idx = orig_narration.index("-")
                narration, payee = (
                    orig_narration[:hypen_idx].strip(),
                    orig_narration[hypen_idx + 1 :].strip(),
                )
            else:
                narration = orig_narration
                payee = None

            metadata = data.new_metadata(file.name, lineno)
            tags = set()

            if card_number == "":
                my_warn(f"Empty card number", lineno, entry)
                tags.add("needs-confirmation")
                account1 = (
                    last_account if last_account is not None else "Assets:Unknown"
                )
            else:
                account1 = find_account_by_card_number(self.config, card_number)
                my_assert(account1, f"Unknown card number {card_number}", lineno, None)
                last_account = account1

            if expense != "":
                units = -units

            if trans_date != "":
                date = parse(trans_date)
                if post_date != "":
                    metadata["post_date"] = post_date
            else:
                date = parse(post_date)
                # transaction date is empty

            if in_blacklist(self.config, orig_narration):
                print(
                    f"Item skipped due to blacklist: {date} {orig_narration} [{units}]",
                    file=sys.stderr,
                )
                continue

            if m := match_destination_and_metadata(
                self.config, orig_narration, payee
            ):  # match twice with narration
                (account2, new_meta, new_tags) = m
                metadata.update(new_meta)
                tags = tags.union(new_tags)
            if account2 is None:
                account2 = unknown_account(self.config, expense)

            price = None
            if "还款成功" in narration:
                if t := self.repayment_tag(account1, narration):
                    tags.add(t)

                rate = self.rate
                if m := re.search(r"汇率([0-9.]+)", narration):
                    rate = float(m.group(1))

                if currency != "CNY" and rate is not None and self.extract_repayment_rate(account1, narration):
                    price = amount.Amount(D(rate), "CNY")


            # backward compat
            if "授权批准" in narration:  # 还款
                tags.add("maybe-repayment")
            # Assume transfer from the first debit card?
            # if "Bank of China Mobile Client" in narration and units1.number > 0:
            #     account2 = f"Assets:Card:BoC:{self.config['card_accounts']['Assets:Card']['BoC'][0]}"
            #     # Swap for deduplication
            #     account1, account2 = account2, account1
            #     units1 = -units1

            txn = data.Transaction(
                meta=metadata,
                date=date.date(),
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
                        price=price,
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
