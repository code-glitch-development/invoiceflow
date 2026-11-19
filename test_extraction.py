from datetime import date, timedelta
from io import BytesIO
import shutil
import subprocess
import unittest
from unittest.mock import patch

from invoice_extraction import (Extraction, ExtractionError, FIELD_KEYS, MAX_BYTES,
                                apply_uploaded_invoice, extract_invoice, money_value,
                                parse_invoice_text, prefill_values)


def invoice_lines(reference='AUTO-TEST-001'):
    return ['FACTURE', reference, 'Fournisseur : Atelier Exemple', 'SIREN : 123 456 789',
            'Client : Groupe Client', 'SIREN : 987 654 321',
            'Date : ' + (date.today() - timedelta(days=2)).strftime('%d/%m/%Y'),
            'Echeance : ' + (date.today() + timedelta(days=45)).strftime('%d/%m/%Y'),
            'Total HT : 350,00 EUR', 'TVA : 70,00 EUR', 'Total TTC : 420,00 EUR']


def text_pdf(lines=None, pages=1, password=None):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica'),
                             NameObject('/Encoding'): NameObject('/WinAnsiEncoding')})
    for _ in range(pages):
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
            NameObject('/F1'): writer._add_object(font)})})
        commands = ['BT /F1 12 Tf 40 790 Td']
        for line in lines or invoice_lines():
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            commands.append('(' + escaped + ') Tj 0 -22 Td')
        commands.append('ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode('cp1252'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def invoice_image(kind='PNG'):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1500, 950), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    for index, line in enumerate(['Invoice No: OCR-2026-007', 'Supplier: Demo Supplier',
                                  'Buyer: Demo Buyer', 'Total TTC: 420.00 EUR']):
        draw.text((70, 80 + index * 130), line, fill='black', font=font)
    output = BytesIO()
    image.save(output, format=kind)
    image.close()
    return output.getvalue()


class ExtractionTests(unittest.TestCase):
    def test_labelled_french_invoice_and_supplier_siren(self):
        result = parse_invoice_text('\n'.join(invoice_lines()))
        self.assertEqual(result.fields['seller'], 'Atelier Exemple')
        self.assertEqual(result.fields['buyer'], 'Groupe Client')
        self.assertEqual(result.fields['siren'], '123456789')
        self.assertEqual(result.fields['reference'], 'AUTO-TEST-001')
        self.assertEqual(result.fields['amount'], 420)
        self.assertEqual(result.fields['issued'], date.today() - timedelta(days=2))
        self.assertEqual(result.fields['due'], date.today() + timedelta(days=45))

    def test_english_invoice_and_siret(self):
        result = parse_invoice_text('Invoice No: INV-2026-007\nSupplier: Supplier Ltd\n'
                                    'SIRET: 123 456 789 00012\nBill to: Buyer Ltd\n'
                                    'Invoice date: 2026-11-19\nDue date: 2026-12-19\n'
                                    'Grand total: EUR 1,234.56')
        self.assertEqual(result.fields['reference'], 'INV-2026-007')
        self.assertEqual(result.fields['siren'], '123456789')
        self.assertEqual(result.fields['buyer'], 'Buyer Ltd')
        self.assertEqual(result.fields['amount'], 1234.56)

    def test_no_guesses_from_unlabelled_numbers_or_ht(self):
        result = parse_invoice_text('2026-11-19\nCommande : CMD-123\nTotal HT : 350,00 EUR\nTVA : 70,00 EUR')
        self.assertEqual(result.fields, {})

    def test_native_pdf_and_no_ocr_for_selectable_text(self):
        with patch('invoice_extraction.ocr_image', side_effect=AssertionError('OCR should not run')):
            result = extract_invoice(text_pdf(), 'invoice.pdf')
        self.assertEqual(result.fields['reference'], 'AUTO-TEST-001')
        self.assertEqual(result.fields['amount'], 420)
        self.assertFalse(result.used_ocr)

    def test_local_money_formats(self):
        for value in ['1 234,56', '1\u202f234,56', '1.234,56', '1,234.56', '1234.56']:
            self.assertEqual(money_value(value), 1234.56)

    def test_face_value_before_remaining_balance(self):
        result = parse_invoice_text('Total TTC : 420,00 EUR\nNet a payer : 200,00 EUR')
        self.assertEqual(result.fields['amount'], 420)

    def test_conflicting_amounts_and_references_are_not_filled(self):
        result = parse_invoice_text('Facture n° ABC-001\nFacture n° ABC-002\n'
                                    'Total TTC : 420,00\nTotal TTC : 600,00')
        self.assertNotIn('amount', result.fields)
        self.assertNotIn('reference', result.fields)
        self.assertTrue(result.warnings)

    def test_non_euro_currency_not_silently_treated_as_euros(self):
        result = parse_invoice_text('Invoice No: USD-001\nTotal due: 123.45 USD')
        self.assertNotIn('amount', result.fields)
        self.assertTrue(result.warnings)

    def test_buyer_siren_not_reused_for_supplier(self):
        result = parse_invoice_text('Fournisseur : Atelier Test\nClient : Client Test\nSIREN : 987654321')
        self.assertNotIn('siren', result.fields)

    def test_invalid_dates_remain_unfilled(self):
        result = parse_invoice_text('Date : 31/02/2026\nEcheance : 99/99/2026')
        self.assertNotIn('issued', result.fields)
        self.assertNotIn('due', result.fields)

    def test_expired_dates_and_missing_amount_are_empty(self):
        result = Extraction(fields={'issued': date(2030, 1, 1), 'due': date(2025, 1, 1)})
        values, applied, warnings = prefill_values(result, today=date(2026, 11, 19))
        self.assertIsNone(values[FIELD_KEYS['issued']])
        self.assertIsNone(values[FIELD_KEYS['due']])
        self.assertIsNone(values[FIELD_KEYS['amount']])
        self.assertEqual(applied, [])
        self.assertEqual(len(warnings), 2)

    def test_encrypted_and_invalid_documents(self):
        for data in [b'', b'invalid', text_pdf(password='secret'), b'a' * (MAX_BYTES + 1)]:
            with self.assertRaises(ExtractionError):
                extract_invoice(data, 'invoice.pdf')

    def test_analysis_page_limit_is_explicit(self):
        result = extract_invoice(text_pdf(pages=4), 'long.pdf')
        self.assertEqual(result.fields['amount'], 420)
        self.assertIn('Only the first three pages were analysed. Check the remaining pages manually.', result.warnings)

    def test_missing_ocr_keeps_manual_entry_available(self):
        with patch('invoice_extraction.subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ExtractionError, 'unavailable'):
                extract_invoice(invoice_image(), 'invoice.png')

    def test_timed_out_ocr_is_a_readable_error(self):
        with patch('invoice_extraction.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 15)):
            with self.assertRaisesRegex(ExtractionError, 'timed out'):
                extract_invoice(invoice_image(), 'invoice.png')

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR binary is not installed.')
    def test_real_ocr_png_and_jpeg(self):
        for kind in ['PNG', 'JPEG']:
            result = extract_invoice(invoice_image(kind), 'invoice.' + kind.lower())
            self.assertTrue(result.used_ocr)
            self.assertEqual(result.fields.get('reference'), 'OCR-2026-007')
            self.assertEqual(result.fields.get('amount'), 420)

    @unittest.skipUnless(shutil.which('tesseract'), 'OCR binary is not installed.')
    def test_real_ocr_scanned_pdf(self):
        from PIL import Image
        with Image.open(BytesIO(invoice_image())) as image:
            output = BytesIO()
            image.save(output, format='PDF')
        result = extract_invoice(output.getvalue(), 'scan.pdf')
        self.assertTrue(result.used_ocr)
        self.assertEqual(result.fields.get('reference'), 'OCR-2026-007')
        self.assertEqual(result.fields.get('amount'), 420)

    def test_same_file_keeps_manual_edits_and_new_file_clears_stale_fields(self):
        state = {}
        data = text_pdf()
        self.assertTrue(apply_uploaded_invoice(state, data, 'invoice.pdf'))
        state['ui_sme_name'] = 'Manually corrected supplier'
        state['ui_invoice_amount'] = 444.0
        self.assertFalse(apply_uploaded_invoice(state, data, 'invoice.pdf'))
        self.assertEqual(state['ui_sme_name'], 'Manually corrected supplier')
        self.assertEqual(state['ui_invoice_amount'], 444.0)
        self.assertTrue(apply_uploaded_invoice(state, text_pdf(['Invoice No: REPLACEMENT-002']), 'other.pdf'))
        self.assertEqual(state['ui_invoice_reference'], 'REPLACEMENT-002')
        self.assertEqual(state['ui_sme_name'], '')
        self.assertIsNone(state['ui_invoice_amount'])

    def test_bad_replacement_does_not_keep_previous_invoice_values(self):
        state = {'ui_invoice_reference': 'OLD', 'ui_invoice_amount': 10000,
                 'ui_simulate_verified_sme_identity': True}
        apply_uploaded_invoice(state, b'invalid file', 'bad.pdf')
        self.assertEqual(state['ui_invoice_reference'], '')
        self.assertIsNone(state['ui_invoice_amount'])
        self.assertFalse(state['ui_simulate_verified_sme_identity'])
        self.assertTrue(state['invoice_prefill']['warnings'])


if __name__ == '__main__':
    unittest.main()
