"""Initialize the SQLite wallet store and import legacy JSON data if present."""

from storage import WalletStore


if __name__ == '__main__':
    store = WalletStore()
    print(f'SQLite wallet database is ready at: {store.path}')
    store.close()
