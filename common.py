import re
import sys
import typing


card_tail_pattern = re.compile(r".*银行.*\(([0-9]{4})\)")
common_date_pattern = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})")

# a map from currency name(chinese) to currency code(ISO 4217)
currency_code_map = {
    "人民币": "CNY",
    "港币": "HKD",
    "澳门元": "MOP",
    "美元": "USD",
    "日元": "JPY",
    "韩元": "KRW",
    "欧元": "EUR",
    "英镑": "GBP",
    "加拿大元": "CAD",
    "澳大利亚元": "AUD",
}

SAME_AS_NARRATION = object()


class BillDetailMapping(typing.NamedTuple):
    # used to match an item's narration
    narration_keywords: typing.Optional[list[str]] = None
    # used to match an item's payee
    payee_keywords: typing.Optional[list[str]] = None
    # destination account (None means not specified)
    destination_account: typing.Optional[str] = None
    # tags to append in bill item
    additional_tags: typing.Optional[list[str]] = None
    # other metadata to append in bill
    additional_metadata: typing.Optional[dict[str, object]] = None
    # priority (larger means higher priority, 0 means lowest)
    priority: int = 0
    # match logic ("OR" or "AND")
    match_logic: str = "OR"

    def canonicalize(self):
        tags = set(self.additional_tags) if self.additional_tags else set()
        metadata = self.additional_metadata.copy() if self.additional_metadata else {}
        return self.destination_account, metadata, tags, self.priority

    def match(
        self, desc: str, payee: str
    ) -> tuple[typing.Optional[str], dict[str, object], set[str], int]:
        assert self.match_logic == "OR" or self.match_logic == "AND"

        # match narration first
        narration_match = False
        if desc is not None and self.narration_keywords is not None:
            for keyword in self.narration_keywords:
                if keyword in desc:
                    narration_match = True
                    break

        # then try payee
        payee_match = False
        if payee is not None and self.payee_keywords is not None:
            keywords = (
                self.narration_keywords
                if self.payee_keywords is SAME_AS_NARRATION
                else self.payee_keywords
            )
            for keyword in keywords:
                if keyword in payee:
                    payee_match = True
                    break

        if self.match_logic == "OR" and (narration_match or payee_match):
            return self.canonicalize()
        elif self.match_logic == "AND" and narration_match and payee_match:
            return self.canonicalize()
        return None, {}, set(), 0


def match_card_tail(src):
    assert type(src) == str
    m = card_tail_pattern.match(src)
    return m[1] if m else None


def open_pdf(config, name):
    import fitz

    doc = fitz.open(name)
    if doc.is_encrypted:
        for password in config["pdf_passwords"]:
            doc.authenticate(password)
        if doc.is_encrypted:
            return None
    return doc


def find_account_by_card_number(config, card_number):
    if isinstance(card_number, int):
        card_number = str(card_number)
    for prefix, accounts in config["card_accounts"].items():
        for bank, numbers in accounts.items():
            if card_number in numbers:
                return f"{prefix}:{bank}:{card_number}"

    return None


def match_destination_and_metadata(config, desc, payee):
    account = None
    mapping = None
    priority = 0
    metadata = {}
    tags = set()

    # merge all possible results
    for m in config["detail_mappings"]:
        _mapping: BillDetailMapping = m
        new_account, new_metadata, new_tags, new_priority = _mapping.match(desc, payee)
        # check compatibility
        if account is None or new_priority > priority:
            account, mapping, priority = new_account, m, new_priority
        elif new_account is not None and new_priority == priority:
            if new_account.startswith(account):
                # new account is deeper than or equal to current account
                account, mapping = new_account, m
            elif not account.startswith(new_account):
                my_warn(
                    f"""Conflict destination accounts found for narration {desc} and payee {payee}:
Old account {account} from {mapping}
New account {new_account} from {m}

""",
                    0,
                    "",
                )

        metadata.update(new_metadata)
        tags.update(new_tags)

    return account, metadata, tags


def match_currency_code(currency_name):
    return (
        currency_code_map[currency_name] if currency_name in currency_code_map else None
    )


def unknown_account(config, expense) -> str:
    return (
        config["unknown_expense_account"]
        if expense
        else config["unknown_income_account"]
    )


def in_blacklist(config, narration):
    for b in config["importers"]["card_narration_whitelist"]:
        if b in narration:
            return False
    for b in config["importers"]["card_narration_blacklist"]:
        if b in narration:
            return True
    return False


def my_assert(cond, msg, lineno, row):
    assert cond, f"{msg} on line {lineno}:\n{row}"


def my_warn(msg, lineno, row):
    print(f"WARNING: {msg} on line {lineno}:\n{row}\n", file=sys.stderr)
