from copy import deepcopy
from datetime import date, timedelta
import math
import unittest

from engine import configure_interest, confirm, finance, new_invoice, settle
from future_value import continuous_future_value, investor_valuation, round_value, valuation_today


def funded_invoice():
    today = valuation_today()
    invoice = new_invoice([], seller='Test SME', siren='987654321', buyer='Test Buyer',
                          reference='FV-001', amount=10000, issued=today-timedelta(days=500),
                          due=today+timedelta(days=60), documents=True, identity=True,
                          strength='Strong', history='On time')
    confirm(invoice, True)
    finance(invoice, 4, False, 80, annual_interest_rate=5,
            financed_on=today-timedelta(days=365))
    return invoice


class FutureValueTests(unittest.TestCase):
    def test_formula_percentage_conversion_and_fractional_year(self):
        self.assertEqual(round_value(continuous_future_value(10000, 1, 5)), 10512.71)
        self.assertAlmostEqual(continuous_future_value(10000, 0.5, 5), 10000 * math.exp(0.025))

    def test_zero_time_rate_and_capital(self):
        self.assertEqual(continuous_future_value(10000, 0, 5), 10000)
        self.assertEqual(continuous_future_value(10000, 20, 0), 10000)
        self.assertEqual(continuous_future_value(0, 100000, 100), 0)

    def test_successive_periods_match_total_period(self):
        previous = continuous_future_value(10000, 0.3, 5)
        self.assertAlmostEqual(continuous_future_value(previous, 0.7, 5),
                               continuous_future_value(10000, 1, 5))

    def test_invalid_and_overflow_inputs(self):
        for args in [(-1, 1, 5), (100, -1, 5), (100, 1, -1), (100, 1, 101),
                     (float('nan'), 1, 5), (100, float('inf'), 5),
                     (100, 1, float('nan')), ('invalid', 1, 5), (100, 100000, 100)]:
            with self.assertRaises(ValueError):
                continuous_future_value(*args)

    def test_actual_days_over_365_and_original_advance(self):
        invoice = funded_invoice()
        result = investor_valuation(invoice)
        self.assertEqual(result['days'], 365)
        self.assertEqual(result['years'], 1)
        self.assertEqual(result['principal'], 9600)
        self.assertEqual(result['future_value'], round_value(9600 * math.exp(.05)))
        self.assertEqual(result['interest'], round_value(9600 * math.exp(.05) - 9600))

    def test_leap_year_uses_actual_days_and_fixed_365_denominator(self):
        invoice = funded_invoice()
        invoice['financing']['financed_on'] = '2024-01-01'
        result = investor_valuation(invoice, date(2025, 1, 1))
        self.assertEqual(result['days'], 366)
        self.assertEqual(result['years'], 366/365)

    def test_rendering_is_read_only_and_does_not_double_compound(self):
        invoice = funded_invoice()
        before = deepcopy(invoice)
        first = investor_valuation(invoice)
        second = investor_valuation(invoice)
        self.assertEqual(first, second)
        self.assertEqual(before, invoice)
        tomorrow = investor_valuation(invoice, valuation_today()+timedelta(days=1))
        self.assertEqual(tomorrow['days'], 366)

    def test_payment_stops_future_growth(self):
        invoice = funded_invoice()
        paid = valuation_today()-timedelta(days=30)
        settle(invoice, 'Paid', paid_on=paid)
        today = investor_valuation(invoice)
        future = investor_valuation(invoice, valuation_today()+timedelta(days=365))
        self.assertEqual(today, future)
        self.assertEqual(today['days'], 335)
        self.assertTrue(today['stopped_at_payment'])
        self.assertEqual(invoice['financing']['paid_on'], paid.isoformat())

    def test_late_payment_and_dispute_do_not_create_collected_income(self):
        invoice = funded_invoice()
        for outcome in ['Late payment', 'Dispute', 'Insolvency']:
            settle(invoice, outcome)
            self.assertEqual(invoice['status'], 'Financed')
            self.assertEqual(investor_valuation(invoice)['days'], 365)
            self.assertNotIn('paid_on', invoice['financing'])

    def test_legacy_funding_requires_explicit_dates_and_rate(self):
        invoice = funded_invoice()
        start = date.fromisoformat(invoice['financing'].pop('financed_on'))
        invoice['financing'].pop('annual_interest_rate')
        before = deepcopy(invoice)
        self.assertIsNone(investor_valuation(invoice))
        self.assertEqual(invoice, before)
        configure_interest(invoice, 5, start)
        self.assertIsNotNone(investor_valuation(invoice))

    def test_legacy_paid_invoice_requires_payment_date(self):
        invoice = funded_invoice()
        invoice.update(outcome='Paid', status='Closed')
        self.assertIsNone(investor_valuation(invoice))
        start = date.fromisoformat(invoice['financing']['financed_on'])
        with self.assertRaises(ValueError):
            configure_interest(invoice, 5, start)
        configure_interest(invoice, 5, start, valuation_today())
        self.assertIsNotNone(investor_valuation(invoice))

    def test_saved_start_cannot_change_but_rate_can(self):
        invoice = funded_invoice()
        start = date.fromisoformat(invoice['financing']['financed_on'])
        before = deepcopy(invoice)
        with self.assertRaises(ValueError):
            configure_interest(invoice, 5, start+timedelta(days=1))
        self.assertEqual(before, invoice)
        configure_interest(invoice, 8, start)
        self.assertEqual(invoice['financing']['annual_interest_rate'], 8)
        self.assertEqual(invoice['financing']['advance'], before['financing']['advance'])
        self.assertEqual(invoice['financing']['fee'], before['financing']['fee'])

    def test_invalid_dates_rejected_without_mutating_records(self):
        invoice = funded_invoice()
        before = deepcopy(invoice)
        for paid in [valuation_today()+timedelta(days=1), date(2000, 1, 1)]:
            with self.assertRaises(ValueError):
                settle(invoice, 'Paid', paid_on=paid)
            self.assertEqual(invoice, before)
        with self.assertRaises(ValueError):
            investor_valuation(invoice, date(2000, 1, 1))

    def test_unfinanced_invoice_has_no_investor_valuation(self):
        self.assertIsNone(investor_valuation({'financing': None}))


if __name__ == '__main__':
    unittest.main()
