from copy import deepcopy
from datetime import date
import math
import unittest

from portfolio import holding_yield_percent, portfolio_summary, financed_annual_rate


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

    def test_global_return_weights_capital_and_excludes_unfinanced_invoices(self):
        records = [self.invoice('small', advance=900, amount=1000),
                   self.invoice('large', advance=9900, amount=10000),
                   dict(self.invoice('unfunded', amount=100000), financing=None)]
        result = portfolio_summary(records)
        self.assertEqual(result['total_capital_advanced'], 10800)
        self.assertEqual(result['projected_gross_gain'], 200)
        self.assertAlmostEqual(result['projected_return_percent'], 100 * 200 / 10800)
        self.assertIsNone(result['realized_return_percent'])

    def test_paid_and_unpaid_returns_have_separate_denominators(self):
        records = [self.invoice('paid', advance=800, amount=1000, outcome='Paid', status='Closed'),
                   self.invoice('open', advance=900, amount=1000)]
        result = portfolio_summary(records)
        self.assertEqual(result['outstanding_capital'], 900)
        self.assertEqual(result['realized_return_percent'], 25)
        self.assertAlmostEqual(result['projected_return_percent'], 100 * 300 / 1700)
        self.assertEqual(result['projected_gross_gain'], 300)

    def test_annual_average_uses_original_cashflows_and_capital_weights(self):
        first = self.invoice('small', advance=900, amount=1000, due='2027-01-01')
        second = self.invoice('large', advance=9900, amount=10000, due='2027-07-02')
        for i in (first, second):
            i['financing']['financed_on'] = '2026-01-01'
        first['financing']['pricing'] = dict(expected_payment_on='2027-01-01')
        expected = (900 * math.log(1000 / 900) * 100 +
                    9900 * math.log(10000 / 9900) * 100 * 365 / 547) / 10800
        result = portfolio_summary([first, second], date(2026, 11, 22))
        self.assertAlmostEqual(result['weighted_annual_rate_percent'], expected)
        self.assertNotEqual(result['weighted_annual_rate_percent'], 90)
        self.assertEqual(result['weighted_annual_rate_percent'],
                         portfolio_summary([first, second], date(2026, 12, 22))['weighted_annual_rate_percent'])

    def test_annual_rate_uses_saved_expected_date_and_excludes_paid_invoices(self):
        invoice = self.invoice('open', due='2026-06-30')
        invoice['financing']['financed_on'] = '2026-01-01'
        invoice['financing']['pricing'] = dict(expected_payment_on='2027-01-01')
        paid = self.invoice('paid', amount=5000, advance=100, outcome='Paid', status='Closed')
        result = portfolio_summary([invoice, paid])
        self.assertAlmostEqual(result['weighted_annual_rate_percent'], 100 * math.log(1000 / 960))
        self.assertEqual(result['annual_missing_count'], 0)

    def test_missing_annual_data_does_not_silently_exclude_part_of_portfolio(self):
        first, second = self.invoice('valid'), self.invoice('legacy')
        first['financing']['financed_on'] = '2026-01-01'
        result = portfolio_summary([first, second])
        self.assertIsNone(result['weighted_annual_rate_percent'])
        self.assertEqual(result['annual_missing_count'], 1)
        self.assertAlmostEqual(result['projected_return_percent'], 100 * 80 / 1920)
        second['financing']['financed_on'] = second['due']
        self.assertIsNone(financed_annual_rate(second))

    def test_empty_returns_are_unavailable_and_zero_gain_is_zero_percent(self):
        empty = portfolio_summary([])
        for key in ('projected_return_percent', 'realized_return_percent', 'weighted_annual_rate_percent'):
            self.assertIsNone(empty[key])
        zero = self.invoice('zero', advance=1000, amount=1000)
        zero['financing']['financed_on'] = '2026-01-01'
        self.assertEqual(portfolio_summary([zero])['projected_return_percent'], 0)
        self.assertEqual(portfolio_summary([zero])['weighted_annual_rate_percent'], 0)


if __name__ == '__main__':
    unittest.main()
