#!/usr/bin/env python3
"""Create a private PostgreSQL backup and optionally prove restore in a disposable DB."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Restore only into a new disposable database, then remove it.')
    parser.add_argument('--directory', type=Path, default=Path.home()/'.antarescrm-deploy-backups'/'automatic')
    args = parser.parse_args()
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    if not url.drivername.startswith('postgresql'): raise SystemExit('Backup operacional requer PostgreSQL.')
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = args.directory/('antares-' + stamp + '-' + secrets.token_hex(3) + '.dump')
    environment = {**os.environ}
    for key,value in {'PGHOST':url.host,'PGPORT':url.port,'PGUSER':url.username,'PGPASSWORD':url.password}.items():
        if value is not None: environment[key] = str(value)
    for key in ('sslmode','sslrootcert','sslcert','sslkey'):
        if key in url.query: environment['PG' + key.upper()] = str(url.query[key])
    # Restrict permissions before pg_dump opens the destination.
    target.touch(mode=0o600, exist_ok=False)
    try:
        subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl','--dbname',url.database,'--file',str(target)],env=environment,check=True,capture_output=True)
        subprocess.run(['pg_restore','--list',str(target)],env=environment,check=True,capture_output=True)
        if args.verify:
            name = 'antares_restore_test_' + secrets.token_hex(6)
            # psycopg uses PG* values as libpq defaults, without logging credentials.
            saved = {key:os.environ.get(key) for key in environment if key.startswith('PG')}
            try:
                os.environ.update({key:value for key,value in environment.items() if key.startswith('PG')})
                with psycopg.connect(dbname='postgres',autocommit=True) as connection:
                    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                try:
                    subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-acl','--dbname',name,str(target)],env=environment,check=True,capture_output=True)
                    with psycopg.connect(dbname=name) as connection:
                        count = connection.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema = %s',('public',)).fetchone()[0]
                        if count < 1: raise RuntimeError('A restauração não contém tabelas.')
                finally:
                    with psycopg.connect(dbname='postgres',autocommit=True) as connection:
                        connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            finally:
                for key,value in saved.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
        record = {'created_at':datetime.now(timezone.utc).isoformat(),'path':str(target),'bytes':target.stat().st_size,'restore_verified':args.verify}
        temporary = args.directory/'latest.json.tmp'
        temporary.write_text(json.dumps(record,ensure_ascii=False)); temporary.chmod(0o600)
        temporary.replace(args.directory/'latest.json')
        print(json.dumps(record,ensure_ascii=False))
    except Exception:
        # Failed/incomplete archives stay private for diagnosis; do not overwrite a successful status.
        print('Falha no backup ou na validação. O banco original não foi restaurado nem modificado.',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__': main()
