# Copy this file to china_bean_importer_config.py and place along side your import config

config = {

    'source': {
        'alipay': {
            "account": "Assets:Alipay",
            "huabei_account": "Liabilities:Alipay:HuaBei",
            "yuebao_account": "Assets:Alipay:YueBao",
        },
        'wechat': {

        }
    },

    'card_accounts': {
        'Liabilities:Card': {
            "BoC": ["1234", "5678"],
            "CMB": ["1111", "2222"],
        },
        'Assets:Card': {
            "BoC": ["4321", "8765"],
            "CMB": ["3333", "4444"],
        }
    },

    'pdf_passwords': ["123456"],

    # account matching
    'unknown_expense_account': 'Expenses:Unknown',
    'unknown_income_account': 'Income:Unknown',

    'destination_accounts': {
        # expenses
        "京东": "Expenses:JD",
        "中铁网络": "Expenses:Travel:Train",
        "AWS": "Expenses:Cloud:AWS",
        "AmazonWebServices": "Expenses:Cloud:AWS",
        "App Store": "Expenses:Apple:AppStore",
        "AppleCare": "Expenses:Apple:AppleCare",
        "iCloud": "Expenses:Apple:ICloud",
        # income
        "工资": "Income:Company"
    },
}