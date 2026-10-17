# Wallet CLI

A local command-line personal finance tracker for recording income and expenses, monitoring spending, and managing monthly budgets.

## Features

- Register and log in with email and a salted PBKDF2 password hash
- Add, view, search, edit, and delete transactions
- Keep the account balance in sync when transactions are added, edited, or deleted
- Add an optional note to each transaction
- View all-time and monthly income, expenses, category totals, and net cash flow
- Set category budgets and review spending for any month
- Export the signed-in user's transactions to CSV
- Create and restore SQLite database backups
- Migrate existing `TRANSACTIONS.json` data to SQLite on first launch

## Run

Python 3.10 or later is recommended. Install the two existing validation dependencies, then run the CLI:

```powershell
pip install zxcvbn email-validator
python wallet.py
```

The database uses Python's built-in `sqlite3`; no database server is required.

## Storage and migration

The app stores its database in `wallet.sqlite3` beside `wallet.py`. On first launch, if that database has no users and `TRANSACTIONS.json` exists, the app imports the users and transactions. Existing balances are preserved during import. After the import succeeds, plaintext `password` properties are removed from the legacy JSON file; login continues to use the existing stored salt and hash.

SQLite tables store users, transactions, and monthly category budgets. Passwords are not stored in plaintext. Email addresses are unique regardless of letter case.

Backups are SQLite files under `backups/`. Restoring a backup first creates a safety backup of the current database. CSV exports are saved under `exports/` and contain only the signed-in user's transactions.

Application events are written to the SQLite `logs` table and to `logs/wallet.log`. The file log rotates at 1 MB and keeps up to five older files; the database retains the latest 5,000 events. Passwords, email addresses, notes, and transaction amounts are excluded from log messages.

## Tests

Run the isolated SQLite tests with:

```powershell
python -m unittest tests.py
```

The tests use temporary databases and do not access `wallet.sqlite3` or the live JSON archive.

## Account menu

1. Add transaction
2. View transactions
3. View balance
4. Edit transaction
5. Delete transaction
6. All-time or monthly report
7. Search and filter transactions
8. Set or view budgets
9. Export transactions to CSV
10. Back up or restore the SQLite database
11. Change password

## Project files

- `wallet.py` — CLI, reports, transaction actions, budgets, and CSV export
- `storage.py` — SQLite schema, JSON migration, balance-safe transaction updates, and backups
- `logging_config.py` — rotating file logging setup
- `tests.py` — isolated tests for migration, balance updates, filters, budgets, backups, and duplicate emails
- `modules.py` — email validation and password hashing / strength helpers
- `TRANSACTIONS.json` — legacy import source; retained as a sanitized archive after migration
- `rewrite_transactions.py` — opens the app's SQLite store and performs the one-time legacy import if needed

The database and backup files contain personal financial information. Keep them in a private folder and include them in backups only where appropriate.
