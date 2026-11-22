"""Transactional SQLite persistence for the shared demo workspace."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3


class StorageError(ValueError):
    pass


class InvoiceStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def transaction(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=10)
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise StorageError('Duplicate detected: supplier reference or file already exists in the database.') from exc
        except (sqlite3.Error, OSError) as exc:
            raise StorageError('The database is unavailable. No changes were saved. Please try again.') from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def payload(invoice):
        return json.dumps({k: v for k, v in invoice.items() if k != '_version'}, ensure_ascii=False)

    def initialize(self, initial):
        # Mark initialization separately: an empty workspace must remain empty on reload.
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY, invoice_key TEXT NOT NULL UNIQUE,
                file_hash TEXT, payload TEXT NOT NULL, version INTEGER NOT NULL)''')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_invoice_file ON invoices(file_hash) WHERE file_hash IS NOT NULL")
            if db.execute("SELECT value FROM metadata WHERE key = 'initialized'").fetchone() is None:
                for invoice in initial:
                    self._insert(db, invoice)
                db.execute("INSERT INTO metadata VALUES ('initialized', '1')")

    def _insert(self, db, invoice):
        db.execute('INSERT INTO invoices VALUES (?, ?, ?, ?, 1)',
                   (invoice['id'], invoice['key'], invoice['file_hash'] or None, self.payload(invoice)))

    def load(self):
        with self.transaction() as db:
            rows = db.execute('SELECT payload, version FROM invoices ORDER BY rowid').fetchall()
        try:
            return [dict(json.loads(payload), _version=version) for payload, version in rows]
        except (ValueError, TypeError) as exc:
            raise StorageError('Saved data could not be read. Restore a database backup before continuing.') from exc

    def add(self, invoice):
        with self.transaction() as db:
            self._insert(db, invoice)
        return dict(deepcopy(invoice), _version=1)

    def update(self, invoice):
        version = invoice.get('_version')
        with self.transaction() as db:
            result = db.execute('''UPDATE invoices SET payload = ?, invoice_key = ?, file_hash = ?, version = version + 1
                                   WHERE id = ? AND version = ?''',
                                (self.payload(invoice), invoice['key'], invoice['file_hash'] or None, invoice['id'], version))
            if result.rowcount != 1:
                raise StorageError('This invoice changed in another session. Reload the latest data before trying again.')
        return dict(deepcopy(invoice), _version=version + 1)

    def reset(self, invoices):
        with self.transaction() as db:
            db.execute('DELETE FROM invoices')
            for invoice in invoices:
                self._insert(db, invoice)

    def remove_builtin_demo_invoices(self):
        """One-time cleanup of known shipped samples; preserve user invoice records."""
        from demo_catalog import builtin_demo_identities
        from engine import canonical
        marker = 'builtin-demo-cleanup-v1'
        identities = builtin_demo_identities()
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM metadata WHERE key = ?', (marker,)).fetchone():
                return 0
            removed = 0
            for identifier, payload in db.execute('SELECT id, payload FROM invoices').fetchall():
                invoice = json.loads(payload)
                identity = (invoice.get('key'), canonical(invoice.get('seller', '')),
                            canonical(invoice.get('buyer', '')))
                if identity in identities and not invoice.get('file_hash'):
                    db.execute('DELETE FROM invoices WHERE id = ?', (identifier,))
                    removed += 1
            db.execute('INSERT INTO metadata VALUES (?, ?)', (marker, '1'))
        return removed

    def remove_auto_supplier_batch(self):
        """Remove the accidental auto-inserted ten-supplier batch, once per database."""
        marker = 'remove-auto-ten-supplier-batch-v1'
        source = 'requested-ten-suppliers-v1'
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM metadata WHERE key = ?', (marker,)).fetchone():
                return 0
            removed = 0
            for identifier, payload in db.execute('SELECT id, payload FROM invoices').fetchall():
                invoice = json.loads(payload)
                if invoice.get('demo_source') == source and not invoice.get('file_hash'):
                    db.execute('DELETE FROM invoices WHERE id = ?', (identifier,))
                    removed += 1
            db.execute('INSERT INTO metadata VALUES (?, ?)', (marker, '1'))
        return removed

    def finance_selection(self, review):
        """Recheck the reviewed portfolio and fund the whole batch atomically."""
        from opportunities import review_selection
        from engine import finance_with_risk_pricing
        from risk_pricing import price_invoice
        with self.transaction() as db:
            rows = db.execute('SELECT payload, version FROM invoices ORDER BY rowid').fetchall()
            latest = [dict(json.loads(payload), _version=version) for payload, version in rows]
            if {i['id']: i['_version'] for i in latest} != review['versions']:
                raise StorageError('The selection changed. Review the latest offers before confirming.')
            by_id = {i['id']: i for i in latest}
            repriced = []
            for entry in review['rows']:
                invoice = by_id[entry['invoice']['id']]
                report = price_invoice(invoice, entry['report']['assumptions'])
                if report['snapshot_hash'] != entry['report']['snapshot_hash']:
                    raise StorageError('The selection changed. Review the latest offers before confirming.')
                repriced.append(dict(invoice=invoice, report=report, scenario=entry['scenario']))
            checked = review_selection(repriced, [e['invoice']['id'] for e in repriced], review['budget'], latest)
            saved = []
            for entry in checked['rows']:
                invoice = entry['invoice']
                finance_with_risk_pricing(invoice, entry['report']['assumptions'], False, 0)
                result = db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ? AND version = ?',
                    (self.payload(invoice), invoice['id'], invoice['_version']))
                if result.rowcount != 1:
                    raise StorageError('The selection changed. Review the latest offers before confirming.')
                saved.append(dict(invoice, _version=invoice['_version'] + 1))
        return saved

    def add_examples(self):
        from opportunities import extra_examples
        with self.transaction() as db:
            existing = [json.loads(row[0]) for row in db.execute('SELECT payload FROM invoices')]
            additions = extra_examples(existing)
            for invoice in additions:
                self._insert(db, invoice)
        return len(additions)

    def populate_demo_catalog(self, *, once=False):
        """Append missing fictional samples atomically, optionally once per database."""
        from demo_catalog import CATALOG_VERSION, catalog_examples
        with self.transaction() as db:
            if once and db.execute('SELECT 1 FROM metadata WHERE key = ?', (CATALOG_VERSION,)).fetchone():
                return 0
            existing = [json.loads(row[0]) for row in db.execute('SELECT payload FROM invoices')]
            additions = catalog_examples(existing)
            for invoice in additions:
                self._insert(db, invoice)
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?, ?)', (CATALOG_VERSION, '1'))
        return len(additions)
