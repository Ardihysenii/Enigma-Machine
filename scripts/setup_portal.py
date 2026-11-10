"""Run after setting ENIGMA_DATABASE_URL. Never include its value in source files."""
import argparse
import os
from pathlib import Path
import secrets
import sys
import uuid
import psycopg
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Apply the additive college-portal schema.')
    parser.add_argument('--admin-email', help='Create the first administrator if it does not already exist.')
    parser.add_argument('--credentials-file', help='Private path outside the repository for generated starter credentials.')
    args = parser.parse_args()
    dsn = os.environ.get('ENIGMA_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not dsn:
        raise SystemExit('Set ENIGMA_DATABASE_URL before running setup.')
    if args.admin_email and not args.credentials_file:
        raise SystemExit('Provide --credentials-file outside the repository for generated administrator access.')
    output = Path(args.credentials_file).resolve() if args.credentials_file else None
    if output and (output.is_relative_to(ROOT) or output.exists()):
        raise SystemExit('Use a new private credentials path outside the repository.')
    email = args.admin_email.strip().lower() if args.admin_email else None
    if email and ('@' not in email or len(email)>254):
        raise SystemExit('Enter a valid administrator email.')
    password = None
    try:
        with psycopg.connect(dsn, connect_timeout=15) as connection:
            connection.execute((ROOT/'database'/'schema.sql').read_text(encoding='utf-8'), prepare=False)
            for code,title in [('SEC101','Information Security'),('SEC102','Secure Systems')]:
                connection.execute('INSERT INTO enigma_portal.courses(id,code,title) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING',(str(uuid.uuid4()),code,title))
            if email:
                connection.execute('SELECT pg_advisory_xact_lock(74420301)')
                exists=connection.execute("SELECT 1 FROM enigma_portal.users WHERE role='admin' AND active LIMIT 1").fetchone()
                if not exists:
                    password=secrets.token_urlsafe(24)
                    identifier=str(uuid.uuid4())
                    connection.execute("INSERT INTO enigma_portal.users(id,name,email,password_hash,role) VALUES(%s,%s,%s,%s,'admin')",(identifier,'ENIGMA Administrator',email,generate_password_hash(password)))
                    connection.execute("INSERT INTO enigma_portal.audit_events(actor_id,actor_name,action,allowed,target) VALUES(%s,%s,'administrator_bootstrapped',true,'initial_setup')",(identifier,'ENIGMA Administrator'))
                    # Exclusive creation avoids replacing any previous private access file.
                    with output.open('x',encoding='utf-8') as private_file:
                        private_file.write('ENIGMA college portal — starter administrator\n\nPortal: https://enigma-machine-seven.vercel.app/college\nEmail: '+email+'\nPassword: '+password+'\n\nKeep this file private. These credentials are not stored in the GitHub repository.\n')
        print('Portal migration applied. Existing data preserved. '+('Starter access saved to the private credentials file.' if password else 'No administrator credentials changed.'))
    except psycopg.Error as error:
        # Database errors may contain connection metadata; do not echo connection strings.
        raise SystemExit('Database setup failed ('+type(error).__name__+').')

if __name__=='__main__':
    main()
