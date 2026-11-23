"""Company-level annual accounts, independent of the presence of invoices."""
from copy import deepcopy
from hashlib import sha256
import json

from engine import canonical
from financial_risk import prepare_buyer_accounts, validate_accounts


def buyer_profile_id(company):
    return 'BUYER-' + sha256(canonical(company).encode()).hexdigest()[:24]


def _exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def load_buyer_profile(store, company):
    if not company.strip():
        raise ValueError('Select the buyer company named on this invoice.')
    identifier = buyer_profile_id(company)
    with store.transaction() as db:
        row = db.execute('SELECT payload, version FROM buyer_profiles WHERE id=?', (identifier,)).fetchone() if _exists(db, 'buyer_profiles') else None
    if row:
        return dict(json.loads(row[0]), _version=row[1])
    return dict(id=identifier, buyer=company, status='Profile', financing=None, _version=0)


def profile_statement_document(store, profile):
    with store.transaction() as db:
        row = db.execute('SELECT sha256, content FROM buyer_profile_documents WHERE profile_id=?', (profile['id'],)).fetchone() if _exists(db, 'buyer_profile_documents') else None
    if row and row[0] == profile.get('buyer_accounts', {}).get('document', {}).get('sha256') and sha256(row[1]).hexdigest() == row[0]:
        return row[1]
    return None


def _sync_profiles(db, store):
    if not _exists(db, 'buyer_profiles') or not _exists(db, 'buyer_profile_documents'):
        return 0
    profiles = {}
    for payload, version, digest, content in db.execute('SELECT p.payload,p.version,d.sha256,d.content FROM buyer_profiles p JOIN buyer_profile_documents d ON p.id=d.profile_id'):
        profile = json.loads(payload)
        if digest == sha256(content).hexdigest() == profile.get('buyer_accounts', {}).get('document', {}).get('sha256'):
            profiles[canonical(profile['buyer'])] = (profile, version, content)
    changed = 0
    for identifier, payload in db.execute('SELECT id,payload FROM invoices').fetchall():
        invoice = json.loads(payload)
        matched = profiles.get(canonical(invoice['buyer']))
        if not matched or invoice.get('financing') or invoice['status'] in ('Financed', 'Closed'):
            continue
        profile, version, content = matched
        previous = invoice.get('buyer_accounts', {})
        # Preserve invoice-specific assessments; update only previously linked profile copies.
        if previous and (previous.get('buyer_profile_id') != profile['id'] or previous.get('buyer_profile_version') == version):
            continue
        accounts = deepcopy(profile['buyer_accounts'])
        try:
            validate_accounts(accounts, invoice['buyer'])
        except ValueError:
            continue
        accounts.update(buyer_profile_id=profile['id'], buyer_profile_version=version)
        invoice['buyer_accounts'] = accounts
        db.execute('CREATE TABLE IF NOT EXISTS buyer_account_documents (invoice_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL)')
        db.execute('INSERT OR REPLACE INTO buyer_account_documents VALUES (?,?,?)', (identifier, accounts['document']['sha256'], content))
        db.execute('UPDATE invoices SET payload=?,version=version+1 WHERE id=?', (store.payload(invoice), identifier))
        changed += 1
    return changed


def sync_buyer_profile_accounts(store):
    """Attach archived company accounts to new/unassessed invoices; never reprice funding."""
    with store.transaction() as db:
        return _sync_profiles(db, store)


def save_buyer_profile_accounts(store, profile, accounts, document_bytes=None, filename=None):
    candidate = prepare_buyer_accounts(profile, accounts, document_bytes, filename)
    if profile['id'] != buyer_profile_id(profile['buyer']):
        raise ValueError('Select the buyer company named on this invoice.')
    with store.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS buyer_profiles (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS buyer_profile_documents (profile_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,content BLOB NOT NULL)')
        row = db.execute('SELECT version FROM buyer_profiles WHERE id=?', (profile['id'],)).fetchone()
        version = row[0] if row else 0
        if version != profile.get('_version'):
            raise ValueError('This invoice changed in another session. Reload the latest data before trying again.')
        if document_bytes is None:
            archived = db.execute('SELECT sha256,content FROM buyer_profile_documents WHERE profile_id=?', (profile['id'],)).fetchone()
            if not archived or archived[0] != candidate['document']['sha256'] or sha256(archived[1]).hexdigest() != archived[0]:
                raise ValueError('Attach the buyer annual statements as a PDF before calculating the indicator.')
        else:
            db.execute('INSERT OR REPLACE INTO buyer_profile_documents VALUES (?,?,?)', (profile['id'], candidate['document']['sha256'], document_bytes))
        saved = dict(profile, buyer_accounts=candidate)
        db.execute('INSERT OR REPLACE INTO buyer_profiles VALUES (?,?,?)', (profile['id'], store.payload(saved), version+1))
        _sync_profiles(db, store)
