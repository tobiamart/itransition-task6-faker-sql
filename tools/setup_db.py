"""Create the faker schema, functions and lookup data in a PostgreSQL database.

Usage: python tools/setup_db.py [DATABASE_URL]   (default: $DATABASE_URL, else a local pgserver instance)
"""
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
FILES = ['01_schema.sql', '02_functions.sql', '03_data.sql']


def database_url():
    if len(sys.argv) > 1:
        return sys.argv[1]
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    import pgserver  # local development only
    return pgserver.get_server(str(ROOT / '.pgdata'), cleanup_mode=None).get_uri()


def main():
    url = database_url()
    with psycopg.connect(url, autocommit=True) as conn:
        for name in FILES:
            conn.execute((ROOT / 'sql' / name).read_text(encoding='utf-8'))
            print('applied', name)
        counts = conn.execute(
            'SELECT (SELECT count(*) FROM faker.names), (SELECT count(*) FROM faker.words),'
            ' (SELECT count(*) FROM faker.formats), (SELECT count(*) FROM faker.picks)').fetchone()
        print('names %d, words %d, formats %d, picks %d' % counts)


if __name__ == '__main__':
    main()
