import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

POSTGRES_DSN = os.getenv('POSTGRES_DSN') or (
    f"dbname={os.getenv('POSTGRES_DB', 'nanoredproxy')} user={os.getenv('POSTGRES_USER', 'nanored')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'nanored')} host={os.getenv('POSTGRES_HOST', 'postgres')} port={os.getenv('POSTGRES_PORT', '5432')}"
)

@contextmanager
def get_conn():
    conn = psycopg.connect(POSTGRES_DSN, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
