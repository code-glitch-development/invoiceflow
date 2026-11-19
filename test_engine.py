import unittest
from datetime import date, timedelta
from engine import seed, new_invoice, confirm, finance, settle, eligible, quote, loss_scenario, migrate_session, financing_blockers, complete_checks, journey


class WorkflowTests(unittest.TestCase):
    def args(self):
        return dict(seller='SME Test', siren='987654321', buyer='Client Test', reference='TEST-001',
                    amount=10000, issued=date.today(), due=date.today()+timedelta(days=60),
                    documents=True, identity=True, strength='Strong', history='On time')

    def test_existing_french_session(self):
        i = new_invoice([], **self.args())
        confirm(i, True)
        i.update(strength='Solide', history='Ponctuel', buyer_status='Confirmée',
                 status='Validée', note='Customer comment to preserve')
        before = {k: i[k] for k in ('id', 'amount', 'reference', 'record_hash', 'note')}
        migrate_session([i])
        self.assertTrue(eligible(i))
        self.assertEqual(i['buyer_status'], 'Confirmed')
        self.assertEqual(before, {k: i[k] for k in before})
        snapshot = i.copy()
        migrate_session([i])
        self.assertEqual(i, snapshot)

    def test_blockers_and_completion_are_consistent(self):
        args = self.args()
        args.update(identity=False, documents=False)
        invoice = new_invoice([], **args)
        messages = financing_blockers(invoice)
        self.assertIn('Buyer confirmation is missing.', messages)
        self.assertIn('SME identity verification is incomplete.', messages)
        self.assertTrue(any('Supporting documents' in m for m in messages))
        confirm(invoice, True)
        complete_checks(invoice, True, True)
        self.assertEqual(financing_blockers(invoice), [])
        self.assertTrue(eligible(invoice))
        self.assertEqual([done for _, done in journey(invoice)], [True, True, True, False, False])
        finance(invoice, 4, False, 80)
        invoice['due'] = date.today().isoformat()
        self.assertEqual([done for _, done in journey(invoice)], [True, True, True, True, False])
        with self.assertRaises(ValueError):
            complete_checks(invoice, False, False)
        settle(invoice, 'Paid')
        self.assertTrue(all(done for _, done in journey(invoice)))

    def test_dispute_expiry_and_low_score_have_specific_reasons(self):
        args = self.args()
        args.update(strength='Weak', history='Frequent delays')
        invoice = new_invoice([], **args)
        confirm(invoice, False, 'Disputed delivery')
        invoice['due'] = date.today().isoformat()
        reasons = financing_blockers(invoice)
        self.assertIn('The invoice is disputed by the buyer.', reasons)
        self.assertIn('The due date has been reached or has passed.', reasons)
        self.assertTrue(any('below 65/100' in message for message in reasons))
        self.assertFalse(eligible(invoice))

    def test_complete_workflow(self):
        i = new_invoice([], **self.args())
        self.assertFalse(eligible(i))
        with self.assertRaises(ValueError):
            finance(i, 4, False, 80)
        confirm(i, True)
        self.assertTrue(eligible(i))
        finance(i, 4, False, 80)
        self.assertEqual(i['financing']['advance'], 9600)
        with self.assertRaises(ValueError):
            finance(i, 4, False, 80)
        with self.assertRaises(ValueError):
            confirm(i, False, 'Dispute')
        settle(i, 'Late payment')
        self.assertEqual(i['status'], 'Financed')
        settle(i, 'Paid')
        self.assertEqual(i['status'], 'Closed')

    def test_duplicate_reference_and_file(self):
        args = self.args()
        i = new_invoice([], **args, file_bytes=b'example')
        args['reference'] = ' test 001 '
        with self.assertRaises(ValueError):
            new_invoice([i], **args)
        args['reference'] = 'OTHER'
        with self.assertRaises(ValueError):
            new_invoice([i], **args, file_bytes=b'example')

    def test_block_missing_checks_and_low_score(self):
        for field, value in [('identity', False), ('documents', False), ('strength', 'Weak')]:
            args = self.args()
            args[field] = value
            if field == 'strength':
                args['history'] = 'Frequent delays'
            i = new_invoice([], **args)
            confirm(i, True)
            self.assertFalse(eligible(i))
        i = new_invoice([], **self.args())
        confirm(i, True)
        i['due'] = date.today().isoformat()
        self.assertFalse(eligible(i))

    def test_dispute(self):
        i = new_invoice([], **self.args())
        with self.assertRaises(ValueError):
            confirm(i, False)
        confirm(i, False, 'Delivery disputed')
        self.assertFalse(eligible(i))

    def test_money_and_losses(self):
        self.assertEqual(quote(10000, 4), dict(amount=10000, fee=400, advance=9600))
        self.assertEqual(quote(123.45, 3)['advance'], 119.75)
        r = loss_scenario(10000, 4, 80)
        self.assertEqual(r['indemnity'], 8000)
        self.assertEqual(r['residual'], 1600)
        self.assertEqual(loss_scenario(10000, 4, 100)['residual'], 0)
        self.assertEqual(loss_scenario(10000, 4, 0)['residual'], 9600)
        self.assertEqual(loss_scenario(10000, 4, 80, True)['lender_exposure'], 1600)

    def test_invalid_and_seed(self):
        for patch in [dict(siren='abc'), dict(amount=-1), dict(due=date.today()), dict(seller='')]:
            args = self.args()
            args.update(patch)
            with self.assertRaises(ValueError):
                new_invoice([], **args)
        self.assertEqual(len(seed()), 4)


if __name__ == '__main__':
    unittest.main()
