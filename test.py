import uuid
import datetime  as dt

# print(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
# print(20 if [] else 'empty')

import zxcvbn
import json
from modules import check_pass_strength,validate_email,get_total_income_and_expenses
db = 'TRANSACTIONS.json'

try:
    with open(db, 'r') as file:
        database = json.load(file)
except FileNotFoundError:
    database = {}


# print(get_total_income_and_expenses(database,'0facbc41'))
user_id = '0facbc41'

# print(validate_email('silasmulama406@gmail.com'))


# print(check_pass_strength('12345678'))
from wallet import INCOME_CATEGORIES,EXPENSE_CATEGORIES

new_cat = {}
all_categories=[]
for category in database[user_id]['transactions']:
    if category['type'] == 'Expense':
        all_categories.append({'category_title':category['category'],'category_amount':category['amount']})
    
for cate in all_categories:
    if cate['category_title'] in new_cat:
        new_cat[cate['category_title']]+=cate['category_amount']
    else:
        new_cat[cate['category_title']]=cate['category_amount']

largest = max(list(new_cat.values()))
smallest = min(list(new_cat.values()))
for category,amount in new_cat.items():
    if amount == largest:
        print(f"Top Spending Category: {category}({amount})")
    elif amount == smallest:
        print(f"Bottom Spending Category: {category}({amount})")

