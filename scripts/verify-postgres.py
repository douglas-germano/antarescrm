"""Run PostgreSQL integration tests in a newly created disposable database."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import psycopg
from psycopg import sql
root = Path(__file__).resolve().parents[1]
name = 'antares_test_' + secrets.token_hex(6)
with psycopg.connect('dbname=postgres', autocommit=True) as connection:
    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
try:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_postgres_integration.py', 'tests/test_workflows_postgres.py'], cwd=root/'backend', env={**os.environ, 'ANTARES_POSTGRES_TEST_URL': 'postgresql+psycopg:///' + name})
finally:
    with psycopg.connect('dbname=postgres', autocommit=True) as connection:
        connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
sys.exit(result.returncode)
