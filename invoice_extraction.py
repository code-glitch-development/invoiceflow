"""Local, best-effort invoice extraction. Never validates or submits an invoice."""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import re
import subprocess
from threading import Lock
import unicodedata

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 3
MAX_PIXELS = 16_000_000
PDFIUM_LOCK = Lock()

FIELD_LABELS = {
    'seller': 'SME name', 'siren': 'SIREN · 9-digit format', 'buyer': 'Buyer',
    'reference': 'Invoice reference', 'amount': 'Invoice amount (€)',
    'issued': 'Issue date', 'due': 'Due date',
}
FIELD_KEYS = {
    'seller': 'ui_sme_name', 'siren': 'ui_siren_9_digit_format', 'buyer': 'ui_buyer',
    'reference': 'ui_invoice_reference', 'amount': 'ui_invoice_amount',
    'issued': 'ui_issue_date', 'due': 'ui_due_date',
}


class ExtractionError(ValueError):
    """Public errors contain no file contents or underlying exception details."""


@dataclass
class Extraction:
    fields: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    used_ocr: bool = False


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c)).casefold()


def money_value(value):
    value = re.sub(r'[\s\u00a0\u202f]', '', value)
    if ',' in value and '.' in value:
        separator = ',' if value.rfind(',') > value.rfind('.') else '.'
        value = value.replace('.' if separator == ',' else ',', '').replace(separator, '.')
    elif ',' in value or '.' in value:
        separator = ',' if ',' in value else '.'
        parts = value.split(separator)
        if len(parts[-1]) == 3:
            value = ''.join(parts)
        else:
            value = ''.join(parts[:-1]) + '.' + parts[-1]
    try:
        result = Decimal(value)
        return float(result) if result.is_finite() and result > 0 else None
    except InvalidOperation:
        return None


DATE_TOKEN = r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})'


def date_value(value):
    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y']:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_invoice_text(text):
    """Only labelled values are proposed. Conflicting values remain empty."""
    result = Extraction()
    # Keep line boundaries: an empty label may be followed by its value.
    original = text.replace('\r\n', '\n').replace('\r', '\n')[:100_000]
    normalized = folded(original)

    def unique(name, values):
        values = list(dict.fromkeys(v for v in values if v is not None and v != ''))
        if len(values) == 1:
            result.fields[name] = values[0]
        elif len(values) > 1:
            result.warnings.append('Conflicting values were detected. Complete the affected fields manually.')

    references = []
    patterns = [
        r'(?:facture|invoice)\s*(?:n[°ºo.]|numero|number|no\.?|reference|ref\.?|#)\s*[:#-]?\s*([a-z0-9][a-z0-9._/-]{1,49})',
        r'(?:reference\s+(?:de\s+)?(?:la\s+)?facture|invoice reference|n[°ºo.]\s*(?:de\s+)?facture)\s*[:#-]?\s*([a-z0-9][a-z0-9._/-]{1,49})',
        r'^\s*(?:facture|invoice)\s*[:#]?\s*\n?\s*([a-z0-9][a-z0-9._/-]{1,49})\s*$',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.MULTILINE):
            token = original[match.start(1):match.end(1)]
            if any(c.isdigit() for c in token) and not date_value(token):
                references.append(token)
    unique('reference', references)

    for name, label in [
        ('issued', r'(?:date\s*(?:de\s*(?:la\s*)?facture|d.emission|de facturation)?|invoice date|issue date|issued(?: on)?)'),
        ('due', r'(?:date\s*d.echeance|echeance(?:\s+simulee)?|due date|payment due|a regler avant le)'),
    ]:
        values = [date_value(m.group(1)) for m in re.finditer(
            r'(?m)^\s*' + label + r'\s*:?\s*(' + DATE_TOKEN + r')', normalized)]
        unique(name, values)

    # Prefer the face value including tax over a remaining balance after a deposit.
    number = r'(\d[\d \t\u00a0\u202f.,]*\d|\d)'
    for label in [r'(?:total\s*(?:t\.?t\.?c\.?|including tax)|montant\s*t\.?t\.?c\.?|grand total|invoice total)',
                  r'(?:net\s*a\s*payer|total\s*a\s*payer|montant\s*a\s*payer|amount due|total due|balance due)',
                  r'total(?!\s*(?:h\.?t\.?|hors|tax|vat))']:
        amounts = [money_value(m.group(1)) for m in re.finditer(
            r'(?m)^\s*' + label + r'\s*:?\s*(?:eur|€)?\s*' + number, normalized)]
        amounts = [v for v in amounts if v is not None]
        if amounts:
            unique('amount', amounts)
            break
    if re.search(r'\b(?:usd|gbp|chf|cad|aud)\b|[$£]', normalized):
        result.fields.pop('amount', None)
        result.warnings.append('A currency other than EUR was detected. Check the amount and currency manually.')

    lines = original.splitlines()
    blocks = {}
    headers = {
        'seller': r'(?:emetteur|fournisseur|vendeur|supplier|seller|from|issued by)(?:\s+fictif)?',
        'buyer': r'(?:client(?:\s+final|\s+fictif)?|destinataire|acheteur|buyer|bill(?:ed)? to|facture a)',
    }
    for name, header in headers.items():
        candidates = []
        for index, line in enumerate(lines):
            match = re.fullmatch(r'\s*' + header + r'\s*(?::\s*(.*))?\s*', folded(line))
            if not match:
                continue
            blocks[name] = index
            if match.group(1):
                candidate = line[match.start(1):match.end(1)].strip()
            else:
                candidate = next((v.strip() for v in lines[index + 1:index + 3] if v.strip()), '')
            if candidate and not re.match(r'(?i)(?:siren|siret|date|total|adresse|invoice|facture)\b', folded(candidate)):
                candidates.append(candidate)
        unique(name, candidates)

    # Do not use a buyer's company number as the supplier's SIREN.
    supplier_text = original
    if 'seller' in blocks:
        start = blocks['seller']
        end = blocks.get('buyer', len(lines))
        supplier_text = '\n'.join(lines[start:end if end > start else len(lines)])
    elif 'buyer' in blocks:
        supplier_text = '\n'.join(lines[:blocks['buyer']])
    sirens = [re.sub(r'\D', '', m.group(1)) for m in re.finditer(
        r'\bsiren\s*:?\s*(\d(?:[ \t.]*\d){8})(?![ \t.]*\d)', folded(supplier_text))]
    if not sirens:
        sirens = [re.sub(r'\D', '', m.group(1))[:9] for m in re.finditer(
            r'\bsiret\s*:?\s*(\d(?:[ \t.]*\d){13})(?![ \t.]*\d)', folded(supplier_text))]
    unique('siren', sirens)
    result.warnings = list(dict.fromkeys(result.warnings))
    return result


def ocr_image(image):
    """Send image bytes over stdin; no shell, third-party service or saved upload."""
    try:
        languages = subprocess.run(['tesseract', '--list-langs'], capture_output=True,
                                   timeout=5, check=True).stdout.decode('utf-8', errors='replace').splitlines()
        supported = [lang for lang in ['fra', 'eng'] if lang in languages]
        if not supported:
            raise ExtractionError('Image recognition is unavailable on this server. Fill in the fields manually.')
        output = BytesIO()
        image.save(output, format='PNG')
        process = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', '+'.join(supported)],
                                 input=output.getvalue(), capture_output=True, timeout=15, check=True)
        return process.stdout.decode('utf-8', errors='replace')
    except FileNotFoundError:
        raise ExtractionError('Image recognition is unavailable on this server. Fill in the fields manually.') from None
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise ExtractionError('Image recognition failed or timed out. Fill in the fields manually.') from None


def render_pdf_page(data, index):
    import pypdfium2 as pdfium
    # PDFium must not be called simultaneously from different Streamlit sessions.
    with PDFIUM_LOCK:
        with pdfium.PdfDocument(data) as document:
            page = document[index]
            try:
                width, height = page.get_size()
                scale = min(2.5, 2400 / max(width, 1), 3200 / max(height, 1))
                bitmap = page.render(scale=scale)
                try:
                    return bitmap.to_pil().copy()
                finally:
                    bitmap.close()
            finally:
                page.close()


def extract_invoice(data, filename):
    from PIL import Image, ImageOps
    if not data or len(data) > MAX_BYTES:
        raise ExtractionError('Use a non-empty PDF, PNG or JPEG file up to 10 MB.')
    warnings, texts, used_ocr = [], [], False
    try:
        if data.startswith(b'%PDF-'):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ExtractionError('This PDF is password-protected. Use an unlocked copy or fill in the fields manually.')
            if len(reader.pages) > MAX_PAGES:
                warnings.append('Only the first three pages were analysed. Check the remaining pages manually.')
            for index, page in enumerate(reader.pages[:MAX_PAGES]):
                text = page.extract_text() or ''
                if len(re.sub(r'\s', '', text)) < 40:
                    try:
                        with render_pdf_page(data, index) as image:
                            text += '\n' + ocr_image(image)
                        used_ocr = True
                    except ExtractionError as exc:
                        warnings.append(str(exc))
                texts.append(text)
        else:
            with Image.open(BytesIO(data)) as source:
                if source.format not in ('PNG', 'JPEG') or source.width * source.height > MAX_PIXELS:
                    raise ExtractionError('Use a PNG or JPEG image with at most 16 million pixels.')
                image = ImageOps.exif_transpose(source)
                try:
                    image.thumbnail((2400, 3200))
                    with image.convert('RGB') as rgb:
                        texts.append(ocr_image(rgb))
                finally:
                    image.close()
            used_ocr = True
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError('The document could not be read. Fill in the fields manually or try another file.') from None
    result = parse_invoice_text('\n'.join(texts))
    result.warnings = list(dict.fromkeys(warnings + result.warnings))
    result.used_ocr = used_ocr
    return result


def prefill_values(result, today=None):
    """A replacement file clears missing fields instead of reusing another invoice."""
    today = today or date.today()
    values = {key: ('' if name in ('seller', 'siren', 'buyer', 'reference') else None)
              for name, key in FIELD_KEYS.items()}
    warnings = list(result.warnings)
    applied = []
    for name, value in result.fields.items():
        if name not in FIELD_KEYS:
            continue
        if name == 'issued' and value > today:
            warnings.append('The detected issue date is in the future. Check it manually.')
            continue
        if name == 'due' and value <= today:
            warnings.append('The detected due date has passed or is today. Check it manually.')
            continue
        if name == 'amount' and value < 1:
            continue
        values[FIELD_KEYS[name]] = value
        applied.append(name)
    return values, applied, list(dict.fromkeys(warnings))


def apply_uploaded_invoice(state, data, filename):
    """Run once per selected file, before form widgets exist. Preserve later edits."""
    digest = hashlib.sha256(data).hexdigest()
    if state.get('invoice_prefill_digest') == digest:
        return False
    try:
        result = extract_invoice(data, filename)
    except ExtractionError as exc:
        result = Extraction(warnings=[str(exc)])
    values, applied, warnings = prefill_values(result)
    state.update(values)
    for key in ['ui_simulate_verified_sme_identity',
                'ui_simulate_complete_documentation_invoice_purchase_order_and_proof_of_delivery']:
        state[key] = False
    state['invoice_prefill_digest'] = digest
    state['invoice_prefill'] = dict(applied=applied, warnings=warnings, used_ocr=result.used_ocr)
    return True
