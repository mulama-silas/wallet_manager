"""SQLite persistence for the personal finance tracker."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'wallet.sqlite3'
LEGACY_JSON = ROOT / 'TRANSACTIONS.json'
DEFAULT_BACKUP_DIR = ROOT / 'backups'
logger = logging.getLogger('wallet.storage')


class WalletStore:
    def __init__(self, path=DEFAULT_DB, legacy_path=LEGACY_JSON, backup_dir=DEFAULT_BACKUP_DIR):
        self.path = Path(path)
        self.legacy_path = Path(legacy_path)
        self.backup_dir = Path(backup_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = self._connect()
        self._create_schema()
        self._migrate_json_if_needed()
        self.log_event('INFO', 'SQLite wallet store opened')

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def _create_schema(self):
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                stored_salt TEXT NOT NULL,
                stored_hash TEXT NOT NULL,
                salary REAL NOT NULL CHECK (salary >= 0),
                balance REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL CHECK (type IN ('Income', 'Expense')),
                amount REAL NOT NULL CHECK (amount > 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
                ON transactions(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_transactions_user_category
                ON transactions(user_id, category);
            CREATE TABLE IF NOT EXISTS budgets (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                monthly_limit REAL NOT NULL CHECK (monthly_limit > 0),
                PRIMARY KEY (user_id, category)
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                event TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
        ''')
        self.connection.commit()

    def log_event(self, level, event, details=''):
        """Write a privacy-safe event to SQLite and the rotating file log."""
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with self.connection:
                self.connection.execute('''
                    INSERT INTO logs (created_at, level, event, details)
                    VALUES (?, ?, ?, ?)
                ''', (created_at, level.upper(), event, details))
                self.connection.execute('''
                    DELETE FROM logs
                    WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 5000)
                ''')
        except sqlite3.Error:
            logger.exception('Could not write an event to the SQLite log table')

        numeric_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(numeric_level, '%s%s', event, f': {details}' if details else '')

    def _migrate_json_if_needed(self):
        user_count = self.connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if user_count or not self.legacy_path.exists():
            return

        with self.legacy_path.open('r', encoding='utf-8') as legacy_file:
            legacy_data = json.load(legacy_file)

        users = []
        transactions = []
        migrated_ids = set()
        seen_emails = set()
        for user_id, user in legacy_data.items():
            salt = user.get('stored_salt')
            hashed = user.get('stored_hash')
            if not salt or not hashed:
                legacy_password = user.get('password')
                if not legacy_password:
                    continue
                from modules import hash_user_password
                salt, hashed = hash_user_password(legacy_password)
            email = user.get('email', '').strip()
            if not email or email.casefold() in seen_emails:
                continue
            seen_emails.add(email.casefold())
            migrated_ids.add(user_id)
            users.append((
                user_id, user.get('name', ''), email, salt, hashed,
                float(user.get('salary', 0)), float(user.get('balance', user.get('salary', 0))),
            ))
            for transaction in user.get('transactions', []):
                transactions.append((
                    transaction['id'], user_id, transaction['type'],
                    float(transaction['amount']), transaction.get('category') or 'Other',
                    transaction.get('description') or '', transaction.get('created_at', ''),
                ))

        with self.connection:
            self.connection.executemany('''
                INSERT OR IGNORE INTO users
                    (id, name, email, stored_salt, stored_hash, salary, balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', users)
            self.connection.executemany('''
                INSERT OR IGNORE INTO transactions
                    (id, user_id, type, amount, category, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', transactions)

        # Keep the legacy JSON as a readable archive but remove any old plaintext passwords.
        if users:
            for user_id, user in legacy_data.items():
                if user_id not in migrated_ids:
                    continue
                user.pop('password', None)
            with self.legacy_path.open('w', encoding='utf-8') as legacy_file:
                json.dump(legacy_data, legacy_file, indent=4, ensure_ascii=False)
            self.log_event(
                'INFO', 'Imported legacy JSON data',
                f'{len(users)} users; {len(transactions)} transactions',
            )

    def close(self):
        self.connection.close()

    def user_by_email(self, email):
        return self.connection.execute(
            'SELECT * FROM users WHERE email = ?', (email.strip(),)
        ).fetchone()

    def user_by_id(self, user_id):
        return self.connection.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()

    def create_user(self, user):
        try:
            with self.connection:
                self.connection.execute('''
                    INSERT INTO users (id, name, email, stored_salt, stored_hash, salary, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user['id'], user['name'], user['email'], user['stored_salt'],
                    user['stored_hash'], user['salary'], user['salary'],
                ))
            self.log_event('INFO', 'Account created')
            return True
        except sqlite3.IntegrityError:
            self.log_event('WARNING', 'Account creation rejected by a database constraint')
            return False

    def change_password(self, user_id, salt, hashed):
        with self.connection:
            self.connection.execute(
                'UPDATE users SET stored_salt = ?, stored_hash = ? WHERE id = ?',
                (salt, hashed, user_id),
            )
        self.log_event('INFO', 'Account password changed')

    def transactions(self, user_id, filters=None):
        filters = filters or {}
        query = 'SELECT * FROM transactions WHERE user_id = ?'
        params = [user_id]
        for key, operator in (
            ('type', '='), ('category', 'LIKE'), ('start_date', '>='),
            ('end_date', '<='), ('min_amount', '>='), ('max_amount', '<='),
        ):
            value = filters.get(key)
            if value is None or value == '':
                continue
            column = 'created_at' if key in ('start_date', 'end_date') else (
                'amount' if key in ('min_amount', 'max_amount') else key
            )
            if key == 'category':
                value = f'%{value}%'
            query += f' AND {column} {operator} ?'
            params.append(value)
        query += ' ORDER BY created_at DESC, id'
        return self.connection.execute(query, params).fetchall()

    def transaction_by_id(self, user_id, transaction_id):
        return self.connection.execute(
            'SELECT * FROM transactions WHERE user_id = ? AND id = ?',
            (user_id, transaction_id),
        ).fetchone()

    def add_transaction(self, user_id, transaction):
        balance_change = transaction['amount'] * (1 if transaction['type'] == 'Income' else -1)
        with self.connection:
            self.connection.execute('''
                INSERT INTO transactions (id, user_id, type, amount, category, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction['id'], user_id, transaction['type'], transaction['amount'],
                transaction['category'], transaction['description'], transaction['created_at'],
            ))
            self.connection.execute(
                'UPDATE users SET balance = balance + ? WHERE id = ?',
                (balance_change, user_id),
            )
        self.log_event('INFO', 'Transaction added')

    def update_transaction(self, user_id, transaction_id, updated):
        current = self.transaction_by_id(user_id, transaction_id)
        if current is None:
            self.log_event('WARNING', 'Transaction edit requested for a missing transaction')
            return False
        old_effect = current['amount'] * (1 if current['type'] == 'Income' else -1)
        new_effect = updated['amount'] * (1 if updated['type'] == 'Income' else -1)
        with self.connection:
            self.connection.execute('''
                UPDATE transactions
                SET type = ?, amount = ?, category = ?, description = ?, created_at = ?
                WHERE user_id = ? AND id = ?
            ''', (
                updated['type'], updated['amount'], updated['category'],
                updated['description'], updated['created_at'], user_id, transaction_id,
            ))
            self.connection.execute(
                'UPDATE users SET balance = balance + ? WHERE id = ?',
                (new_effect - old_effect, user_id),
            )
        self.log_event('INFO', 'Transaction edited')
        return True

    def delete_transaction(self, user_id, transaction_id):
        transaction = self.transaction_by_id(user_id, transaction_id)
        if transaction is None:
            self.log_event('WARNING', 'Transaction deletion requested for a missing transaction')
            return False
        effect = transaction['amount'] * (1 if transaction['type'] == 'Income' else -1)
        with self.connection:
            self.connection.execute(
                'DELETE FROM transactions WHERE user_id = ? AND id = ?',
                (user_id, transaction_id),
            )
            self.connection.execute(
                'UPDATE users SET balance = balance - ? WHERE id = ?',
                (effect, user_id),
            )
        self.log_event('INFO', 'Transaction deleted')
        return True

    def totals(self, user_id, filters=None):
        rows = self.transactions(user_id, filters)
        income = sum(row['amount'] for row in rows if row['type'] == 'Income')
        expenses = sum(row['amount'] for row in rows if row['type'] == 'Expense')
        return income, expenses, len(rows)

    def expense_totals_by_category(self, user_id, filters=None):
        filters = dict(filters or {})
        filters['type'] = 'Expense'
        rows = self.transactions(user_id, filters)
        totals = {}
        for row in rows:
            totals[row['category']] = totals.get(row['category'], 0) + row['amount']
        return totals

    def set_budget(self, user_id, category, monthly_limit):
        with self.connection:
            self.connection.execute('''
                INSERT INTO budgets (user_id, category, monthly_limit)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, category)
                DO UPDATE SET monthly_limit = excluded.monthly_limit
            ''', (user_id, category, monthly_limit))
        self.log_event('INFO', 'Monthly budget saved')

    def budgets(self, user_id):
        return self.connection.execute(
            'SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category',
            (user_id,),
        ).fetchall()

    def budget_spending(self, user_id, category, year, month):
        month_start = f'{year:04d}-{month:02d}-01'
        if month == 12:
            next_month = f'{year + 1:04d}-01-01'
        else:
            next_month = f'{year:04d}-{month + 1:02d}-01'
        return self.connection.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE user_id = ? AND type = 'Expense' AND category = ?
              AND created_at >= ? AND created_at < ?
        ''', (user_id, category, month_start, next_month)).fetchone()[0]

    def create_backup(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_path = self.backup_dir / f'wallet_backup_{stamp}.sqlite3'
        destination = sqlite3.connect(backup_path)
        try:
            self.connection.backup(destination)
        finally:
            destination.close()
        self.log_event('INFO', 'SQLite backup created')
        return backup_path

    def list_backups(self):
        if not self.backup_dir.exists():
            return []
        return sorted(self.backup_dir.glob('wallet_backup_*.sqlite3'), reverse=True)

    def restore_backup(self, backup_path):
        backup_path = Path(backup_path).resolve()
        backup_root = self.backup_dir.resolve()
        if backup_root not in backup_path.parents or not backup_path.is_file():
            raise ValueError('Choose a backup from the backups folder.')

        try:
            check = sqlite3.connect(f'{backup_path.as_uri()}?mode=ro', uri=True)
            try:
                result = check.execute('PRAGMA integrity_check').fetchone()[0]
                tables = {row[0] for row in check.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )}
                if result != 'ok' or not {'users', 'transactions', 'budgets'} <= tables:
                    raise ValueError('That file is not a valid wallet database backup.')
            finally:
                check.close()
        except sqlite3.DatabaseError as error:
            raise ValueError('That file is not a readable SQLite backup.') from error

        self.create_backup()  # Keep a restore-point of the current database.
        self.connection.close()
        try:
            shutil.copy2(backup_path, self.path)
        finally:
            self.connection = self._connect()
            self._create_schema()
        self.log_event('INFO', 'SQLite backup restored')

