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
