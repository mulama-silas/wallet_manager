"""Command-line personal finance tracker."""

import csv
import logging
import os
import sys
import ctypes
from datetime import datetime
from getpass import getpass
from pathlib import Path

from modules import (
    check_pass_strength,
    get_id,
    get_timestamp,
    hash_user_password,
    validate_email,
    verify_password,
)
from storage import WalletStore
from logging_config import configure_logging


EXPENSE_CATEGORIES = [
    'Food', 'Transport', 'Groceries', 'Bills', 'Entertainment',
    'Health', 'Rent', 'Subscriptions', 'Travel',
]
INCOME_CATEGORIES = [
    'Salary', 'Bonus', 'Freelance', 'Investment', 'Interest',
    'Gift', 'Rental Income', 'Commission', 'Business', 'Savings',
]
TRANSACTION_TYPES = ['Expense', 'Income']
logger = logging.getLogger('wallet.cli')


def _terminal_supports_color():
    if os.environ.get('NO_COLOR') or not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.GetStdHandle.argtypes = [ctypes.c_uint]
            kernel32.GetStdHandle.restype = ctypes.c_void_p
            kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
            kernel32.GetConsoleMode.restype = ctypes.c_int
            kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            kernel32.SetConsoleMode.restype = ctypes.c_int
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            if not kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                return False
        except (AttributeError, OSError):
            return False
    return os.environ.get('TERM') != 'dumb'


COLOR_ENABLED = _terminal_supports_color()


def color(text, code):
    return f'\033[{code}m{text}\033[0m' if COLOR_ENABLED else text


def print_billboard():
    """Draw a large, layered terminal logo."""
    glyphs = {
        'W': ('10001', '10001', '10001', '10101', '10101', '10101', '01010'),
        'A': ('01110', '10001', '10001', '11111', '10001', '10001', '10001'),
        'L': ('10000', '10000', '10000', '10000', '10000', '10000', '11111'),
        'E': ('11111', '10000', '10000', '11110', '10000', '10000', '11111'),
        'T': ('11111', '00100', '00100', '00100', '00100', '00100', '00100'),
        'C': ('01111', '10000', '10000', '10000', '10000', '10000', '01111'),
        'I': ('11111', '00100', '00100', '00100', '00100', '00100', '11111'),
    }
    positions = []
    cursor = 0
    for letter in 'WALLET CLI':
        if letter == ' ':
            cursor += 4
            continue
        for row in range(7):
            for column, pixel in enumerate(glyphs[letter][row]):
                if pixel == '1':
                    positions.append((row, cursor + column))
        cursor += 6

    width = cursor + 2
    canvas = [[' ' for _ in range(width)] for _ in range(8)]
    for row, column in positions:
        canvas[row + 1][column + 2] = '░'
    for row, column in positions:
        canvas[row][column] = '█'

    def render_row(row):
        result, segment, previous = [], '', None
        shades = {'█': '94;1', '░': '96'}
        for pixel in row:
            shade = shades.get(pixel)
            if segment and shade != previous:
                result.append(color(segment, previous) if previous else segment)
                segment = ''
            segment += pixel
            previous = shade
        if segment:
            result.append(color(segment, previous) if previous else segment)
        return ''.join(result)

    print()
    print(color('PERSONAL FINANCE  /  YOUR MONEY, IN FOCUS'.center(width), '35;1'))
    for row in canvas:
        print(render_row(row).center(width + 10))
    print()
    print(color('TRACK THOUGHTFULLY.  SPEND CONFIDENTLY.'.center(width), '97;1'))
    print(color('INCOME   •   EXPENSES   •   CLARITY'.center(width), '36'))
    print(color('─' * (width + 10), '34'))
    print()


def choose(options, prompt='Choose an option', allow_cancel=True):
    for index, option in enumerate(options, 1):
        print(f'  {color(str(index), "36;1")}. {option}')
    if allow_cancel:
        print('  0. Cancel')
    while True:
        answer = input(f'{prompt}: ').strip()
        try:
            selected = int(answer)
        except ValueError:
            print('Enter a number from the menu.')
            continue
        if allow_cancel and selected == 0:
            return None
        if 1 <= selected <= len(options):
            return options[selected - 1]
        print('That option is not on the menu.')


def prompt_amount(prompt='Amount', current=None, allow_blank=False):
    while True:
        suffix = f' [{current}]' if current is not None else ''
        answer = input(f'{prompt}{suffix}: ').strip()
        if allow_blank and not answer:
            return current
        try:
            amount = float(answer)
        except ValueError:
            print('Enter a valid number.')
            continue
        if amount <= 0:
            print('Amount must be greater than zero.')
            continue
        return amount


def prompt_date(prompt, current=None, allow_blank=False):
    while True:
        suffix = f' [{current}]' if current else ''
        answer = input(f'{prompt}{suffix} (YYYY-MM-DD): ').strip()
        if allow_blank and not answer:
            return current
        try:
            datetime.strptime(answer, '%Y-%m-%d')
            return answer
        except ValueError:
            print('Enter a date in YYYY-MM-DD format.')


def register_user(store):
    name = input('Name: ').strip()
    while not name:
        print('Name cannot be empty.')
        name = input('Name: ').strip()

    while True:
        email = input('Email: ').strip()
        if not validate_email(email):
            print('Enter a valid email address.')
        elif store.user_by_email(email):
            print('An account with that email already exists.')
        else:
            break

    salary = prompt_amount('Starting balance / salary')
    while True:
        password = getpass('Password (at least 8 characters): ', echo_char='*').strip()
        if len(password) < 8:
            print('Password must be at least 8 characters long.')
            continue
        feedback = check_pass_strength(password)
        if feedback:
            print(feedback)
            continue
        confirmation = getpass('Confirm password: ', echo_char='*').strip()
        if password != confirmation:
            print('Passwords do not match.')
            continue
        break

    salt, hashed = hash_user_password(password)
    created = store.create_user({
        'id': get_id(), 'name': name, 'email': email,
        'stored_salt': salt, 'stored_hash': hashed, 'salary': salary,
    })
    print('Account created.' if created else 'That email is already registered.')


def login_user(store):
    email = input('Email: ').strip()
    user = store.user_by_email(email)
    password = getpass('Password: ', echo_char='*').strip()
    if user and verify_password(user['stored_salt'], user['stored_hash'], password):
        print(f'Welcome, {user["name"]}!')
        store.log_event('INFO', 'Authentication succeeded')
        return user['id']
    print('Invalid email or password.')
    store.log_event('WARNING', 'Authentication failed')
    return None


def add_transaction(store, user_id):
    transaction_type = choose(TRANSACTION_TYPES, 'Transaction type')
    if transaction_type is None:
        return
    amount = prompt_amount()
    categories = EXPENSE_CATEGORIES if transaction_type == 'Expense' else INCOME_CATEGORIES
    category = choose(categories, 'Category')
    if category is None:
        return
    description = input('Note / description (optional): ').strip()
    store.add_transaction(user_id, {
        'id': get_id(), 'type': transaction_type, 'amount': amount,
        'category': category, 'description': description,
        'created_at': get_timestamp(),
    })
    print('Transaction added.')


def display_transactions(rows):
    if not rows:
        print('No matching transactions.')
        return
    print('\n #  DATE                 TYPE      CATEGORY          AMOUNT       NOTE')
    print('─' * 88)
    for index, row in enumerate(rows, 1):
        print(
            f'{index:>2}. {row["created_at"]:<20} {row["type"]:<9} '
            f'{row["category"]:<17} Ksh {row["amount"]:>9.2f}   {row["description"]}'
        )


def select_transaction(store, user_id):
    rows = store.transactions(user_id)
    display_transactions(rows)
    if not rows:
        return None
    while True:
        answer = input('Select transaction number (0 to cancel): ').strip()
        try:
            number = int(answer)
        except ValueError:
            print('Enter a transaction number.')
            continue
        if number == 0:
            return None
        if 1 <= number <= len(rows):
            return rows[number - 1]
        print('That transaction number is not in the list.')


def view_transactions(store, user_id):
    filters = {}
    selection = choose(['All transactions', 'Expenses only', 'Income only'], 'Show')
    if selection is None:
        return
    if selection == 'Expenses only':
        filters['type'] = 'Expense'
    elif selection == 'Income only':
        filters['type'] = 'Income'
    display_transactions(store.transactions(user_id, filters))


def edit_transaction(store, user_id):
    current = select_transaction(store, user_id)
    if current is None:
        return

    print('Press Enter to keep a value; enter - for the note to clear it.')
    new_type = input(f'Type [{current["type"]}] (Expense/Income): ').strip().title()
    if not new_type:
        new_type = current['type']
    while new_type not in TRANSACTION_TYPES:
        new_type = input('Enter Expense or Income: ').strip().title()
    amount = prompt_amount('Amount', current['amount'], allow_blank=True)
    category_options = EXPENSE_CATEGORIES if new_type == 'Expense' else INCOME_CATEGORIES
    print('Categories: ' + ', '.join(category_options))
    category = input(f'Category [{current["category"]}]: ').strip() or current['category']
    if category not in category_options:
        print(f'Using custom category: {category}')
    date_part = current['created_at'][:10]
    new_date = prompt_date('Date', date_part, allow_blank=True)
    time_part = current['created_at'][11:]
    if not time_part:
        time_part = '00:00:00'
    note = input(f'Note [{current["description"]}]: ')
    if note == '':
        note = current['description']
    elif note.strip() == '-':
        note = ''
    store.update_transaction(user_id, current['id'], {
        'type': new_type, 'amount': amount, 'category': category,
        'description': note.strip(), 'created_at': f'{new_date} {time_part}',
    })
    print('Transaction updated; balance adjusted.')


def delete_transaction(store, user_id):
    transaction = select_transaction(store, user_id)
    if transaction is None:
        return
    if input(f'Delete {transaction["category"]} transaction of Ksh {transaction["amount"]:.2f}? (y/N): ').strip().lower() == 'y':
        store.delete_transaction(user_id, transaction['id'])
        print('Transaction deleted; balance adjusted.')


def search_transactions(store, user_id):
    print('Leave a field blank to skip that filter.')
    filters = {}
    transaction_type = input('Type (Expense/Income): ').strip().title()
    if transaction_type:
        if transaction_type not in TRANSACTION_TYPES:
            print('Unknown type; type filter skipped.')
        else:
            filters['type'] = transaction_type
    filters['category'] = input('Category contains: ').strip()
    start = input('From date (YYYY-MM-DD): ').strip()
    end = input('To date (YYYY-MM-DD): ').strip()
    if start:
        try:
            filters['start_date'] = f'{datetime.strptime(start, "%Y-%m-%d").date()} 00:00:00'
        except ValueError:
            print('Invalid start date; filter skipped.')
    if end:
        try:
            filters['end_date'] = f'{datetime.strptime(end, "%Y-%m-%d").date()} 23:59:59'
        except ValueError:
            print('Invalid end date; filter skipped.')
    for key, prompt in (('min_amount', 'Minimum amount'), ('max_amount', 'Maximum amount')):
        value = input(f'{prompt}: ').strip()
        if value:
            try:
                filters[key] = float(value)
            except ValueError:
                print(f'Invalid {prompt.lower()}; filter skipped.')
    display_transactions(store.transactions(user_id, filters))


def _month_input():
    now = datetime.now()
    value = input(f'Month to report (YYYY-MM, default {now:%Y-%m}): ').strip()
    if not value:
        return now.year, now.month
    try:
        parsed = datetime.strptime(value, '%Y-%m')
        return parsed.year, parsed.month
    except ValueError:
        print('Enter month as YYYY-MM.')
        return None


def create_report(store, user_id):
    selection = choose(['All-time summary', 'Monthly summary'], 'Report')
    if selection is None:
        return
    title = 'ALL-TIME REPORT'
    if selection == 'Monthly summary':
        month = _month_input()
        if month is None:
            return
        year, month_number = month
        start = f'{year:04d}-{month_number:02d}-01 00:00:00'
        if month_number == 12:
            end = f'{year + 1:04d}-01-01 00:00:00'
        else:
            end = f'{year:04d}-{month_number + 1:02d}-01 00:00:00'
        rows = store.transactions(user_id)
        rows = [row for row in rows if start <= row['created_at'] < end]
        income = sum(row['amount'] for row in rows if row['type'] == 'Income')
        expenses = sum(row['amount'] for row in rows if row['type'] == 'Expense')
        count = len(rows)
        category_totals = {}
        for row in rows:
            if row['type'] == 'Expense':
                category_totals[row['category']] = category_totals.get(row['category'], 0) + row['amount']
        title = f'{datetime(year, month_number, 1):%B %Y} REPORT'
    else:
        income, expenses, count = store.totals(user_id)
        category_totals = store.expense_totals_by_category(user_id)

    user = store.user_by_id(user_id)
    print(f'\n===== {title} =====')
    print(f'Total income:   Ksh {income:,.2f}')
    print(f'Total expenses: Ksh {expenses:,.2f}')
    print(f'Net:            Ksh {income - expenses:,.2f}')
    print(f'Current balance: Ksh {user["balance"]:,.2f}')
    print(f'Transactions: {count}')
    store.log_event('INFO', 'Wallet report generated')
    if category_totals:
        largest = max(category_totals.values())
        smallest = min(category_totals.values())
        for category, amount in category_totals.items():
            if amount == largest:
                print(f'Top spending category: {category} (Ksh {amount:,.2f})')
        for category, amount in category_totals.items():
            if amount == smallest:
                print(f'Lowest spending category: {category} (Ksh {amount:,.2f})')
    else:
        print('No expenses in this period.')


def budget_menu(store, user_id):
    action = choose(['Set or update a monthly budget', 'View budget progress'], 'Budgets')
    if action is None:
        return
    if action == 'Set or update a monthly budget':
        category = choose(EXPENSE_CATEGORIES, 'Expense category')
        if category is None:
            return
        limit = prompt_amount('Monthly limit')
        store.set_budget(user_id, category, limit)
        print(f'Monthly {category} budget set to Ksh {limit:,.2f}.')
        return

    month = _month_input()
    if month is None:
        return
    year, month_number = month
    budgets = store.budgets(user_id)
    if not budgets:
        print('No budgets set yet.')
        return
    print(f'\nBUDGETS FOR {year:04d}-{month_number:02d}')
    for budget in budgets:
        spent = store.budget_spending(user_id, budget['category'], year, month_number)
        remaining = budget['monthly_limit'] - spent
        status = 'OVER BUDGET' if remaining < 0 else 'within budget'
        print(
            f'{budget["category"]}: Ksh {spent:,.2f} / Ksh {budget["monthly_limit"]:,.2f} '
            f'({status}; Ksh {remaining:,.2f} remaining)'
        )


def export_csv(store, user_id):
    rows = store.transactions(user_id)
    if not rows:
        print('No transactions to export.')
        return
    export_dir = Path(__file__).resolve().parent / 'exports'
    export_dir.mkdir(exist_ok=True)
    user = store.user_by_id(user_id)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    path = export_dir / f'transactions_{user_id}_{stamp}.csv'
    with path.open('w', newline='', encoding='utf-8-sig') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=[
            'id', 'type', 'amount', 'category', 'description', 'created_at',
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})
    print(f'Exported {len(rows)} transactions for {user["name"]} to {path}.')
    store.log_event('INFO', 'CSV export completed')


def backup_menu(store):
    action = choose(['Create SQLite backup', 'Restore a SQLite backup'], 'Database backup')
    if action == 'Create SQLite backup':
        print(f'Backup created: {store.create_backup()}')
        return
    if action != 'Restore a SQLite backup':
        return
    backups = store.list_backups()
    if not backups:
        print('No backups found in the backups folder.')
        return
    for index, path in enumerate(backups, 1):
        print(f'  {index}. {path.name}')
    try:
        selected = int(input('Choose backup number (0 to cancel): ').strip())
    except ValueError:
        print('Enter a number from the list.')
        return
    if selected == 0:
        return
    if not 1 <= selected <= len(backups):
        print('That backup number is not in the list.')
        return
    print('Restoring replaces the current users, transactions, and budgets.')
    if input('Type RESTORE to continue: ').strip() != 'RESTORE':
        print('Restore cancelled.')
        return
    try:
        store.restore_backup(backups[selected - 1])
        print('Backup restored. A safety backup of the previous database was also created.')
    except (OSError, ValueError) as error:
        print(f'Could not restore backup: {error}')


def change_password(store, user_id):
    user = store.user_by_id(user_id)
    current = getpass('Current password: ').strip()
    if not verify_password(user['stored_salt'], user['stored_hash'], current):
        print('Current password is incorrect.')
        return
    while True:
        password = getpass('New password (at least 8 characters): ').strip()
        if len(password) < 8:
            print('Password must be at least 8 characters long.')
            continue
        feedback = check_pass_strength(password)
        if feedback:
            print(feedback)
            continue
        confirmation = getpass('Confirm new password: ').strip()
        if password != confirmation:
            print('Passwords do not match.')
            continue
        salt, hashed = hash_user_password(password)
        store.change_password(user_id, salt, hashed)
        print('Password updated.')
        return


def account_menu(store, user_id):
    actions = [
        'Add transaction', 'View transactions', 'View balance',
        'Edit transaction', 'Delete transaction', 'Reports',
        'Search / filter transactions', 'Budgets', 'Export transactions to CSV',
        'Backup / restore SQLite database', 'Change password',
    ]
    while True:
        user = store.user_by_id(user_id)
        if user is None:
            print('This account is not present in the restored database. Logging out.')
            return
        print(f'\n{color(user["name"], "1;97")}  |  Balance: Ksh {user["balance"]:,.2f}')
        for index, action in enumerate(actions, 1):
            print(f'  {color(str(index), "36;1")}. {action}')
        print('  0. Logout')
        try:
            choice = int(input('Choose an option: ').strip())
        except ValueError:
            print('Enter a number from the menu.')
            continue
        if choice == 0:
            return
        handlers = {
            1: lambda: add_transaction(store, user_id),
            2: lambda: view_transactions(store, user_id),
            3: lambda: print(f'Current balance: Ksh {store.user_by_id(user_id)["balance"]:,.2f}'),
            4: lambda: edit_transaction(store, user_id),
            5: lambda: delete_transaction(store, user_id),
            6: lambda: create_report(store, user_id),
            7: lambda: search_transactions(store, user_id),
            8: lambda: budget_menu(store, user_id),
            9: lambda: export_csv(store, user_id),
            10: lambda: backup_menu(store),
            11: lambda: change_password(store, user_id),
        }
        handler = handlers.get(choice)
        if handler:
            handler()
        else:
            print('Invalid choice.')


def main():
    configure_logging()
    logger.info('Wallet application starting')
    store = None
    try:
        print_billboard()
        store = WalletStore()
        store.log_event('INFO', 'Wallet application started')
        while True:
            print(f'\n{color("GET STARTED", "1;97")}')
            print(f'  {color("1", "32;1")}. Register')
            print(f'  {color("2", "33;1")}. Login')
            print(f'  {color("0", "31;1")}. Exit')
            choice = input('Choose an option: ').strip()
            if choice == '1':
                register_user(store)
            elif choice == '2':
                user_id = login_user(store)
                if user_id:
                    account_menu(store, user_id)
            elif choice == '0':
                print('Goodbye!')
                break
            else:
                print('Invalid choice.')
    except KeyboardInterrupt:
        print('\nGoodbye!')
        if store is not None:
            store.log_event('INFO', 'Wallet application interrupted by user')
        else:
            logger.info('Wallet application interrupted by user')
    except Exception:
        logger.exception('Unexpected wallet application error')
        if store is not None:
            store.log_event('ERROR', 'Unexpected wallet application error')
        print('The app encountered an unexpected error. See logs/wallet.log for details.')
    finally:
        if store is not None:
            store.log_event('INFO', 'Wallet application stopped')
            store.close()
        else:
            logger.info('Wallet application stopped')


if __name__ == '__main__':
    main()
