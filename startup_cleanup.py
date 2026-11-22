"""Startup migrations that work with an already-loaded legacy storage class."""
import json


def remove_auto_supplier_batch(store):
    """Use the stable transaction API, without requiring a new InvoiceStore method."""
    marker = 'remove-auto-ten-supplier-batch-v1'
    source = 'requested-ten-suppliers-v1'
    with store.transaction() as db:
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
