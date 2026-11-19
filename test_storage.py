from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from engine import seed, confirm, finance, settle
from future_value import investor_valuation, valuation_today
from storage import InvoiceStore, StorageError


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'demo.db'
        self.store = InvoiceStore(self.path)
        self.store.initialize(seed())

    def test_reopen_keeps_financing_and_does_not_reseed(self):
        invoice = self.store.load()[0]
        finance(invoice, 4, False, 80)
        saved = self.store.update(invoice)
        reopened = InvoiceStore(self.path)
        reopened.initialize(seed())
        self.assertEqual(reopened.load()[0], saved)
        self.assertEqual(saved['financing']['advance'], 14400)

    def test_interest_rate_funding_and_payment_dates_survive_reopening(self):
        invoice = self.store.load()[0]
        finance(invoice, 4, False, 80, annual_interest_rate=6.5)
        saved = self.store.update(invoice)
        settle(saved, 'Paid')
        paid = self.store.update(saved)
        reopened = InvoiceStore(self.path).load()[0]
        self.assertEqual(reopened, paid)
        self.assertEqual(reopened['financing']['annual_interest_rate'], 6.5)
        self.assertEqual(reopened['financing']['financed_on'], valuation_today().isoformat())
        self.assertEqual(reopened['financing']['paid_on'], valuation_today().isoformat())
        self.assertEqual(investor_valuation(reopened)['interest'], 0)

    def test_stale_update_is_rejected_without_losing_another_invoice(self):
        initial = self.store.load()
        first = deepcopy(initial[0])
        stale = deepcopy(first)
        confirm(first, False, 'Disputed by buyer')
        self.store.update(first)
        confirm(stale, True)
        with self.assertRaises(StorageError):
            InvoiceStore(self.path).update(stale)
        saved = self.store.load()
        self.assertEqual(saved[0]['buyer_status'], 'Disputed')
        self.assertEqual(saved[1], initial[1])

    def test_duplicate_metadata_and_file_across_connections(self):
        invoice = self.store.load()[0]
        duplicate = deepcopy(invoice)
        duplicate['id'] = 'NEW-ID'
        with self.assertRaises(StorageError):
            InvoiceStore(self.path).add(duplicate)
        invoice['file_hash'] = 'same-file-hash'
        self.store.update(invoice)
        duplicate['key'] = 'another-reference'
        duplicate['file_hash'] = 'same-file-hash'
        with self.assertRaises(StorageError):
            InvoiceStore(self.path).add(duplicate)
        self.assertEqual(len(self.store.load()), 4)

    def test_reset_is_atomic_and_stale_invoice_cannot_return(self):
        before = self.store.load()
        invalid = [deepcopy(before[0]), deepcopy(before[0])]
        with self.assertRaises(StorageError):
            self.store.reset(invalid)
        self.assertEqual(self.store.load(), before)
        self.store.reset(seed())
        with self.assertRaises(StorageError):
            self.store.update(before[0])
        self.assertNotEqual(self.store.load()[0]['id'], before[0]['id'])

    def test_empty_workspace_stays_empty_and_failures_are_explicit(self):
        self.store.reset([])
        self.store.initialize(seed())
        self.assertEqual(self.store.load(), [])
        unavailable = InvoiceStore(Path(self.directory.name))
        with self.assertRaisesRegex(StorageError, 'database is unavailable'):
            unavailable.load()


if __name__ == '__main__':
    unittest.main()

