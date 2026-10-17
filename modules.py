import uuid
import datetime as dt
import hashlib
import binascii
import os
import hmac
import zxcvbn
import email_validator as ev
from getpass import getpass

# Utility functions for transaction IDs and timestamps

def get_id() -> str:
    """Return a short unique identifier for a transaction or user."""
    return str(uuid.uuid4()).split('-')[0]


def get_timestamp() -> str:
    """Return the current timestamp in a readable string format."""
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_type(transaction_type_options) -> int:
    """Ask the user to choose a transaction type from the provided options."""
    if not transaction_type_options:
        print('Provide type options!')

    for index, option in enumerate(transaction_type_options):
        print(f"{index+1}. {option}")

    while True:
        try:
            selected_type = int(input('Choose 1 or 2: '))
            if selected_type == 0:
                return None

            if 1 <= selected_type <= len(transaction_type_options):
                return transaction_type_options[selected_type-1]

            print('Invalid Choice!')
        except ValueError:
            print('Please enter a valid number!!')
def get_category(transaction_category_options) -> int:
    """Ask the user to choose a transaction category from the available options."""
    if not transaction_category_options:
        print('Provide type options!')

    print('Choose Category')
    for index, option in enumerate(transaction_category_options):
        print(f"{index+1}. {option}")

    while True:
        try:
            selected_category = int(input('Choose 1 or 2: '))
            if selected_category == 0:
                return None

            if 1 <= selected_category <= len(transaction_category_options):
                return transaction_category_options[selected_category-1]

            print('Invalid Choice!')
        except ValueError:
            print('Please enter a valid number!!')

def get_amount() -> float:
    """Prompt the user for an amount and repeat until a valid number is entered."""
    while True:
        try:
            amount = float(input('Enter Amount: '))
            return amount
        except ValueError:
            print('Enter a valid number!')


def get_description() -> str:
    """Get a transaction description from the user and trim whitespace."""
    description = input('Enter Description: ').strip()
    return description

"""----- PASSWORD VALIDATION OPERATIONS-----"""

def validate_email(email):
    """Validate an email address and return True if it is valid."""
    try:
        ev.validate_email(email, check_deliverability=False)
        return True
    except ev.EmailNotValidError:
        return False
def check_pass_strength(password):
    """Check password strength and return feedback if it is weak."""
    strength = zxcvbn.zxcvbn(password)

    if strength['score'] >= 3:
        return
    warning = strength['feedback'].get('warning') or 'Choose a less predictable password.'
    suggestions = ' '.join(strength['feedback'].get('suggestions', []))
    return f"{warning} {suggestions}".strip()

def hash_user_password(password) -> list:
    """Hash a password with a random salt and return [salt, hashed_password]."""
    salt = os.urandom(16)
    iterations = 100000
    # hash using PBKDF2-HMAC-SHA256
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    hash_salt = binascii.hexlify(salt).decode()
    hashed_password = binascii.hexlify(dk).decode()
    return [hash_salt, hashed_password]


def verify_password(stored_salt, stored_hash, password):
    """Verify a user password against stored salt and hash."""
    salt = binascii.unhexlify(stored_salt)
    user_password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return hmac.compare_digest(binascii.hexlify(user_password_hash).decode(), stored_hash)


def get_user_data(data):
    """Collect new user information, validate it, and store it in the database."""
    name = input('Enter your name: ').strip()
    while True:
        email = input('Enter your email: ').strip()
        if validate_email(email):
            break

    user_id = get_id()
    while True:
        try:
            salary = float(input('Enter your salary: '))
            while True:
                password = getpass('Enter your password: ').strip()
                if len(password) < 8:
                    print('Password must be at least 8 characters long!')
                    continue
                if check_pass_strength(password):
                    print(check_pass_strength(password))
                    continue
                confirm_password = getpass('Confirm your password: ').strip()
                if password != confirm_password:
                    print('Passwords do not match!')
                else:
                    break
            break
        except ValueError:
            print('Enter a valid number for salary!')

    hash_results = hash_user_password(password)
    data[user_id] = {
        'name': name,
        'email': email,
        'stored_salt': hash_results[0],
        'stored_hash': hash_results[1],
        'salary': salary,
        'balance': salary,
        'transactions': [],
    }
    print('User Registered Successfully✅✅')
    return user_id

def login(data):
    """Log in a user by validating email and password."""
    while True:
        email = input('Enter your email: ').strip()
        if validate_email(email):
            break
    password = getpass('Enter your password: ').strip()
    # verify email and password
    for user_id,user_data in data.items():
        if user_data['email'] == email:
            if verify_password(user_data['stored_salt'],user_data['stored_hash'],password):
                print('Login Successful✅✅')
                return user_id
    print('Invalid email or password!')

"""display all transactions"""
def all_transactions(data,user_id):
    index = 0
    for transaction in data[user_id]['transactions']:
        print(
                f"{index+1}. Transaction of type {transaction['type']}, "
                f"amount Ksh {transaction['amount']}, "
                f"categorized as {transaction['category']} "
                f"on {transaction['created_at']}."
            )
        index +=1

"""return selected transaction"""
def get_user_selection(data,user_id):
    transactions = data[user_id]['transactions']
    if not transactions:
        print('No transactions at the moment!')
        return None
    
    # display all transactions
    all_transactions(data,user_id)

    while True:
        try:
            user_choice = int(input('Choose 1,2,...: '))
            if user_choice == 0:
                return None
            
            if 1<=user_choice<=len(transactions):
                return transactions[user_choice-1]['id']
            
        except ValueError:
            print('Enter a valid number!')

def get_total_income_and_expenses(data,user_id):
    final_result = []
    total_income = 0
    total_expenses = 0
    transactions = data[user_id]['transactions']
    _transactions  = len(transactions)
    for transaction in transactions:
        if transaction['type'] == 'Expense':
            total_expenses += transaction['amount']
        elif transaction['type'] == 'Income':
            total_income += transaction['amount']
        else:
            pass
    
    return [total_expenses,total_income,_transactions]

def expense_info(data,user_id):
    new_cat = {}
    all_categories=[]
    for category in data[user_id]['transactions']:
        if category['type'] == 'Expense':
            all_categories.append({'category_title':category['category'],'category_amount':category['amount']})
        
    for cate in all_categories:
        if cate['category_title'] in new_cat:
            new_cat[cate['category_title']]+=cate['category_amount']
        else:
            new_cat[cate['category_title']]=cate['category_amount']
    if not new_cat:
        print("No expense transactions to summarize.")
        return
    largest = max(list(new_cat.values()))
    smallest = min(list(new_cat.values()))
    for category,amount in new_cat.items():
        if amount == largest:
            print(f"Top Spending Category: {category}({amount})")
        elif amount == smallest:
            print(f"Bottom Spending Category: {category}({amount})")

