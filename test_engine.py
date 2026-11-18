import unittest
from datetime import date, timedelta
from engine import seed, new_invoice, confirm, finance, settle, eligible, quote, loss_scenario


class WorkflowTests(unittest.TestCase):
    def args(self):
        return dict(seller='PME Test', siren='987654321', buyer='Client Test', reference='TEST-001',
                    amount=10000, issued=date.today(), due=date.today()+timedelta(days=60),
                    documents=True, identity=True, strength='Solide', history='Ponctuel')

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
            confirm(i, False, 'Litige')
        settle(i, 'Retard')
        self.assertEqual(i['status'], 'Financée')
        settle(i, 'Payée')
        self.assertEqual(i['status'], 'Clôturée')

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
        for field, value in [('identity', False), ('documents', False), ('strength', 'Fragile')]:
            args = self.args()
            args[field] = value
            if field == 'strength':
                args['history'] = 'Retards fréquents'
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
        confirm(i, False, 'Livraison contestée')
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
