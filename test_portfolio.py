from copy import deepcopy
from datetime import date
import unittest

from portfolio import holding_yield_percent, portfolio_summary


class PortfolioTests(unittest.TestCase):
    def invoice(self, reference, *, buyer='Maison Atlas', advance=960, amount=1000,
                due='2026-11-20', outcome=None, status='Financed'):
        return dict(reference=reference, buyer=buyer, amount=amount, due=due,
                    outcome=outcome, status=status,
                    financing=dict(advance=advance, annual_interest_rate=90, coverage=100))

    def test_cashflows_do_not_double_count_paid_capital_or_interest(self):
        records = [self.invoice('unpaid'),
                   self.invoice('paid', amount=2000, advance=1800, outcome='Paid', status='Closed'),
                   dict(self.invoice('unfunded'), financing=None)]
        original = deepcopy(records)
        result = portfolio_summary(records, date(2026, 11, 21))
        self.assertEqual(result['outstanding_capital'], 960)
        self.assertEqual(result['repayments'], 2000)
        self.assertEqual(result['realized_gain'], 200)
        self.assertEqual(result['potential_gain'], 40)
        self.assertEqual(records, original)

    def test_due_today_paid_and_unfinanced_invoices_are_not_overdue(self):
        records = [self.invoice('yesterday'), self.invoice('today', due='2026-11-21'),
                   self.invoice('declared', due='2026-11-25', outcome='Late payment'),
                   self.invoice('paid', outcome='Paid', status='Closed'),
                   dict(self.invoice('unfunded'), financing=None)]
        result = portfolio_summary(records, date(2026, 11, 21))
        self.assertEqual(result['overdue_count'], 2)
        self.assertEqual(result['overdue_capital'], 1920)
        self.assertEqual([i['reference'] for i in result['overdue']], ['yesterday', 'declared'])

    def test_incidents_remain_exposed_without_inventing_recoveries(self):
        records = [self.invoice(event, outcome=event) for event in ('Dispute', 'Insolvency', 'Late payment')]
        result = portfolio_summary(records, date(2026, 11, 21))
        self.assertEqual(result['outstanding_capital'], 2880)
        self.assertEqual(result['potential_gain'], 120)
        self.assertEqual(result['repayments'], 0)
        self.assertEqual(result['realized_gain'], 0)

    def test_exposure_groups_buyer_variants_and_excludes_paid(self):
        records = [self.invoice('a', buyer='Maison Atlas', advance=100),
                   self.invoice('b', buyer=' MAISON ATLAS ', advance=200),
                   self.invoice('c', buyer='Other', advance=100),
                   self.invoice('d', buyer='Other', outcome='Paid', status='Closed')]
        result = portfolio_summary(records, date(2026, 11, 21))
        self.assertEqual([(r['capital'], r['count'], r['share_percent']) for r in result['exposure']],
                         [(300, 2, 75), (100, 1, 25)])

    def test_empty_portfolio_and_gross_holding_return(self):
        result = portfolio_summary([])
        self.assertTrue(all(result[k] == 0 for k in ('outstanding_capital', 'repayments',
            'realized_gain', 'potential_gain', 'overdue_capital', 'overdue_count')))
        self.assertEqual(result['exposure'], [])
        self.assertEqual(holding_yield_percent(1000, 800), 25)


if __name__ == '__main__':
    unittest.main()
