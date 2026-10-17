"""Initialize the SQLite wallet store and import legacy JSON data if present."""

import logging

from storage import WalletStore
from logging_config import configure_logging


if __name__ == '__main__':
    configure_logging()
    logger = logging.getLogger('wallet.migration')
    store = None
    try:
        store = WalletStore()
        print(f'SQLite wallet database is ready at: {store.path}')
    except Exception:
        logger.exception('SQLite initialization or legacy migration failed')
        raise
    finally:
        if store is not None:
            store.close()
