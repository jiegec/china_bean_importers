# Copy this file to china_bean_importer_config.py and place along side
# your import config

from china_bean_importers.common import BillDetailMapping as BDM

config = {
    "importers": {
        "alipay": {
            "account": "Assets:Alipay",
            "huabei_account": "Liabilities:Alipay:HuaBei",
            "douyin_monthly_payment_account": "Liabilities:DouyinMonthlyPayment",
            "yuebao_account": "Assets:Alipay:YuEBao",
            "red_packet_income_account": "Income:Alipay:RedPacket",
            "red_packet_expense_account": "Expenses:Alipay:RedPacket",
            "category_mapping": {
                "交通出行": "Expenses:Travel",
            },
        },
        "wechat": {
            "account": "Assets:WeChat",
            "lingqiantong_account": "Assets:WeChat:LingQianTong",
            "red_packet_income_account": "Income:WeChat:RedPacket",
            "red_packet_expense_account": "Expenses:WeChat:RedPacket",
            "family_card_expense_account": "Expenses:WeChat:FamilyCard",
            "group_payment_expense_account": "Expenses:WeChat:Group",
            "group_payment_income_account": "Income:WeChat:Group",
            "transfer_expense_account": "Expenses:WeChat:Transfer",
            "transfer_income_account": "Income:WeChat:Transfer",
        },
        "thu_ecard": {
            "account": "Assets:Card:THU",
        },
        "hsbc_hk": {
            "account_mapping": {
                "One": "Assets:Bank:HSBC",
                "PULSE": "Liabilities:CreditCards:HSBC:Pulse",
            },
            "use_cnh": False,
        },
        "card_narration_whitelist": ["财付通(银联云闪付)"],
        "card_narration_blacklist": ["支付宝", "财付通", "美团支付"],
    },
    "card_accounts": {
        "Liabilities:Card": {
            "BoC": ["1234", "5678"],
            "CMB": ["1111", "2222"],
        },
        "Assets:Card": {
            "BoC": ["4321", "8765"],
            "CMB": ["3333", "4444"],
        },
    },
    "pdf_passwords": ["123456"],
    # account matching
    "unknown_expense_account": "Expenses:Unknown",
    "unknown_income_account": "Income:Unknown",
    "detail_mappings": [
        BDM(["京东"], [], "Expenses:JD", [], {"platform": "京东"}),
        BDM([], ["饿了么"], "Expenses:Food:Delivery", [], {"platform": "饿了么"}),
        BDM([], ["万龙运动旅游"], None, ["ski"], {}),
    ],
}
