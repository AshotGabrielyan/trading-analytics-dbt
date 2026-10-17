"""Minimal Metabase API client (stdlib only), plus first-run setup.

Credentials live in metabase/.admin_credentials (git-ignored). On a fresh Metabase
they are generated here and the admin account is created through the setup API.
"""
import json
import pathlib
import secrets
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CRED = HERE / '.admin_credentials'
BASE = 'http://localhost:3000'
DB_NAME = 'Trading warehouse'
DB_FILE = '/warehouse/trading.duckdb'  # path inside the container, see docker-compose.yml

_session = None


def _request(method, path, body=None, session=None):
    headers = {'Content-Type': 'application/json'}
    if session:
        headers['X-Metabase-Session'] = session
    req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f'{method} {path} -> {e.code}: {e.read().decode()[:2000]}')


def _credentials():
    return dict(line.split('=', 1) for line in CRED.read_text().split())


def call(method, path, body=None):
    global _session
    if _session is None:
        cfg = _credentials()
        _session = _request('POST', '/api/session', {'username': cfg['email'], 'password': cfg['password']})['id']
    return _request(method, path, body, _session)


def ensure_admin(email, first_name, last_name):
    """Create the admin account on a fresh Metabase; no-op once set up."""
    token = _request('GET', '/api/session/properties').get('setup-token')
    if CRED.exists() or not token:
        return
    password = secrets.token_urlsafe(18)
    CRED.write_text(f'email={email}\npassword={password}\n')
    CRED.chmod(0o600)
    _request('POST', '/api/setup', {
        'token': token,
        'user': {'first_name': first_name, 'last_name': last_name, 'email': email,
                 'password': password, 'password_confirm': password},
        'prefs': {'site_name': 'Trading Analytics', 'allow_tracking': False},
    })
    print(f'created admin {email}; password saved to {CRED}')


def ensure_database():
    """Return the id of the read-only DuckDB connection, creating it and waiting for sync."""
    db = next((d for d in call('GET', '/api/database')['data'] if d['name'] == DB_NAME), None)
    if db is None:
        db = call('POST', '/api/database', {'engine': 'duckdb', 'name': DB_NAME,
                                            'details': {'database_file': DB_FILE, 'read_only': True}})
        print(f'added database connection {DB_NAME}')
    for _ in range(60):
        tables = call('GET', f"/api/database/{db['id']}/metadata")['tables']
        if any(t['schema'] == 'marts' for t in tables):
            return db['id']
        time.sleep(3)
    raise SystemExit('schema sync did not finish; is the warehouse built (dbt build)?')
