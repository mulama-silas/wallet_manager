"""Isolated tests for SQLite persistence and wallet bookkeeping."""

import json
import tempfile
import unittest
from pathlib import Path

from storage import WalletStore


class WalletStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = WalletStore(
            path=self.root / 'wallet.sqlite3',
            legacy_path=self.root / 'TRANSACTIONS.json',
            backup_dir=self.root / 'backups',
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def add_user(self, user_id='user-1', email='person@example.com', balance=10000):
        self.assertTrue(self.store.create_user({
            'id': user_id,
            'name': 'Test User',
            'email': email,
            'stored_salt': 'test-salt',
            'stored_hash': 'test-hash',
            'salary': balance,
        }))
        return user_id

    @staticmethod
    def transaction(transaction_id, kind, amount, category, date, description=''):
        return {
            'id': transaction_id,
            'type': kind,
            'amount': amount,
            'category': category,
            'description': description,
            'created_at': date,
        }

    def test_adding_editing_and_deleting_keep_balance_in_sync(self):
        user_id = self.add_user()
        self.store.add_transaction(user_id, self.transaction(
            'tx-1', 'Expense', 100, 'Food', '2026-05-01 12:00:00', 'Lunch',
        ))
        self.assertEqual(self.store.user_by_id(user_id)['balance'], 9900)

        updated = self.transaction(
            'tx-1', 'Income', 150, 'Bonus', '2026-05-01 12:00:00', 'Correction',
        )
        self.assertTrue(self.store.update_transaction(user_id, 'tx-1', updated))
        self.assertEqual(self.store.user_by_id(user_id)['balance'], 10150)
        self.assertEqual(self.store.transaction_by_id(user_id, 'tx-1')['description'], 'Correction')

        self.assertTrue(self.store.delete_transaction(user_id, 'tx-1'))
        self.assertEqual(self.store.user_by_id(user_id)['balance'], 10000)
        self.assertIsNone(self.store.transaction_by_id(user_id, 'tx-1'))

    def test_filters_and_monthly_category_budget(self):
        user_id = self.add_user()
        self.store.add_transaction(user_id, self.transaction(
            'tx-food', 'Expense', 250, 'Food', '2026-05-05 10:00:00',
        ))
        self.store.add_transaction(user_id, self.transaction(
            'tx-bills', 'Expense', 400, 'Bills', '2026-05-20 10:00:00',
        ))
        self.store.add_transaction(user_id, self.transaction(
            'tx-june', 'Expense', 900, 'Food', '2026-06-01 00:00:00',
        ))

        results = self.store.transactions(user_id, {
            'type': 'Expense', 'category': 'ood',
            'start_date': '2026-05-01 00:00:00',
            'end_date': '2026-05-31 23:59:59',
            'min_amount': 200, 'max_amount': 300,
        })
        self.assertEqual([row['id'] for row in results], ['tx-food'])

        self.store.set_budget(user_id, 'Food', 500)
        self.assertEqual(self.store.budget_spending(user_id, 'Food', 2026, 5), 250)
        self.assertEqual(self.store.budget_spending(user_id, 'Food', 2026, 6), 900)

    def test_legacy_json_migration_preserves_data_and_removes_plaintext_password(self):
        legacy_path = self.root / 'TRANSACTIONS.json'
        legacy = {
            'legacy-user': {
                'name': 'Legacy User',
                'email': 'legacy@example.com',
                'password': 'old-plaintext-password',
                'stored_salt': 'legacy-salt',
                'stored_hash': 'legacy-hash',
                'salary': 1200,
                'balance': 1350,
                'transactions': [{
                    'id': 'legacy-tx', 'type': 'Income', 'amount': 150,
                    'category': 'Bonus', 'created_at': '2026-05-02 09:00:00',
                }],
            },
        }
        legacy_path.write_text(json.dumps(legacy), encoding='utf-8')

        self.store.close()
        self.store = WalletStore(
            path=self.root / 'migrated.sqlite3',
            legacy_path=legacy_path,
            backup_dir=self.root / 'backups',
        )

        user = self.store.user_by_id('legacy-user')
        self.assertEqual(user['balance'], 1350)
        self.assertEqual(self.store.transactions('legacy-user')[0]['id'], 'legacy-tx')
        archived = json.loads(legacy_path.read_text(encoding='utf-8'))
        self.assertNotIn('password', archived['legacy-user'])

    def test_backup_restore_recovers_snapshot_and_creates_safety_backup(self):
        self.add_user()
        backup_path = self.store.create_backup()
        self.add_user('user-2', 'second@example.com', 500)

        self.store.restore_backup(backup_path)

        self.assertIsNotNone(self.store.user_by_id('user-1'))
        self.assertIsNone(self.store.user_by_id('user-2'))
        self.assertEqual(len(self.store.list_backups()), 2)

    def test_email_uniqueness_ignores_case(self):
        self.add_user(email='Person@Example.com')
        created = self.store.create_user({
            'id': 'user-2',
            'name': 'Duplicate',
            'email': 'person@example.com',
            'stored_salt': 'salt',
            'stored_hash': 'hash',
            'salary': 0,
        })
        self.assertFalse(created)


def run_tests():
    unittest.main(module=__name__)


if __name__ == '__main__':
    run_tests()
