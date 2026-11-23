"""Conservative local annual-account extraction. Ambiguity never becomes a zero."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
import re
import math
from invoice_extraction import folded, date_value, DATE_TOKEN, ocr_image, render_pdf_page, ExtractionError

MAX_PAGES=16
MAX_OCR_PAGES=6


@dataclass
class AccountingExtraction:
    fields: dict=field(default_factory=dict)
    values: dict=field(default_factory=dict)
    evidence: dict=field(default_factory=dict)
    warnings: list=field(default_factory=list)
    used_ocr: bool=False


LABELS={
 'total_assets': [r'total\s+(?:de\s+l[’\']?\s*)?actif',r'total\s+assets'],
 'current_assets': [r'(?:total\s+)?actif\s+circulant(?:\s+net)?',r'current\s+assets(?:,?\s+including\s+cash)?'],
 'current_liabilities':[r'(?:total\s+)?(?:dettes|passif)\s+(?:exigibles?\s+)?(?:a|à)\s+(?:moins\s+d[’\']?un\s+an|court\s+terme)',r'(?:total\s+)?current\s+liabilities'],
 'total_liabilities':[r'total\s+(?:du\s+)?passif\s+hors\s+capitaux\s+propres',r'total\s+(?:non.equity\s+)?liabilities'],
 'equity':[r'(?:total\s+des\s+|total\s+)?capitaux\s+propres',r'(?:total\s+)?(?:book\s+(?:value\s+of\s+)?)?equity'],
 'retained_earnings':[r'(?:benefices|resultats)\s+accumules\s+non\s+distribues(?:\s*/\s*pertes)?',r'(?:accumulated\s+)?retained\s+earnings(?:\s*/\s*losses)?'],
 'ebit':[r'ebit(?!da)',r'(?:resultat|benefice)\s+avant\s+interets\s+et\s+impots?',r'earnings\s+before\s+interest\s+and\s+tax(?:es)?'],
}
# Explicit aggregate labels only: a generic TOTAL GENERAL/EBE/net profit is ambiguous.
NUMBER=r'(?:\(?[+−-]?\d(?:[\d .,\u00a0\u202f]*\d)?\)?|[−-])'


def signed_amount(text):
    value=text.strip().replace('−','-').replace('\u00a0',' ').replace('\u202f',' ')
    if value in ('-','—',''):
        return None
    negative=value.startswith('(') and value.endswith(')')
    value=value.strip('()').replace(' ','')
    if ',' in value and '.' in value:
        decimal=',' if value.rfind(',')>value.rfind('.') else '.'
        value=value.replace('.' if decimal==',' else ',','').replace(decimal,'.')
    elif ',' in value:
        parts=value.split(',')
        value=''.join(parts) if len(parts[-1])==3 else ''.join(parts[:-1])+'.'+parts[-1]
    elif value.count('.')>1 or ('.' in value and len(value.rsplit('.',1)[1])==3):
        value=value.replace('.','')
    try:
        result=float(value)
        return (-abs(result) if negative else result) if math.isfinite(result) else None
    except ValueError:
        return None


def _columns(suffix):
    text=suffix.strip().lstrip(':').strip()
    text=re.sub(r'^(?:eur|€)\s*','',text,flags=re.I)
    text=re.sub(r'\s*(?:eur|€)\s*$','',text,flags=re.I)
    if not text:return []
    # Two spaces, tabs or bars preserve column boundaries; single spaces may group thousands.
    parts=[v.strip() for v in re.split(r'\s*\|\s*|\t+| {2,}',text) if v.strip()]
    if len(parts)==1:
        if re.fullmatch(NUMBER,parts[0]):
            # Reject ungrouped, single-space comparative pairs such as 1000000 900000.
            unsigned=parts[0].strip('()').lstrip('+-−')
            if ' ' in unsigned and not re.fullmatch(r'\d{1,3}(?: \d{3})+(?:[,.]\d{1,2})?',unsigned):return []
        else:return []
    if not all(re.fullmatch(NUMBER,v) for v in parts):return []
    return [signed_amount(v) for v in parts]


def comparative_index(lines):
    selected=None
    for line in lines:
        header=folded(line)
        if re.search(r'\b(?:du|from)\b.*\b(?:au|to)\b',header):continue
        dates=[date_value(x) for x in re.findall(DATE_TOKEN,header)]
        if len(dates)==2 and all(dates) and dates[0]!=dates[1]:selected=0 if dates[0]>dates[1] else 1
        years=re.findall(r'\b(?:19|20)\d{2}\b',header)
        if not dates and len(years)==2 and ('|' in header or re.search(r' {2,}|\t',header)) and years[0]!=years[1]:selected=0 if years[0]>years[1] else 1
        if re.search(r'\bn\s*[-−]\s*1\s*(?:\|| {2,}|\t).*?\bn\b(?!\s*[-−]\s*1)',header):selected=1
        elif re.search(r'\b(?:exercice\s+)?n\s*(?:\|| {2,}|\t).*?n\s*[-−]\s*1\b',header):selected=0
    return selected


def parse_account_pages(pages):
    result=AccountingExtraction()
    ends=[];periods=[];candidates={key:[] for key in LABELS};entities=[];sirens=[]
    for page_no,original in enumerate(pages,1):
        lines=original.splitlines(); normal=folded(original)
        for match in re.finditer(r'(?:exercice|periode|financial year|period)[^\n]{0,35}?(?:du|from)\s*('+DATE_TOKEN+r')\s*(?:au|to)\s*('+DATE_TOKEN+r')',normal):
            start,end=map(date_value,match.groups())
            if start and end:periods.append((start,end,page_no))
        for match in re.finditer(r'(?:exercice\s*(?:n\s*)?(?:clos|cloture)(?:\s*le)?|date\s*de\s*cloture|cloture(?:\s*au)?|year\s*ended)\s*[:\-]?\s*('+DATE_TOKEN+r')',normal):
            end=date_value(match.group(1))
            if end:ends.append((end,page_no))
        for line in lines:
            norm=folded(line).strip()
            identity=re.match(r'(?:denomination(?:\s+sociale)?|raison\s+sociale|company\s+name|company\s+named\s+in\s+the\s+accounts)\s*:\s*(.+)$',norm)
            if identity:entities.append((line.split(':',1)[1].strip(),page_no,line))
            number=re.search(r'\bsiren\s*:\s*(\d(?:[ .]*\d){8})(?![ .]*\d)',norm)
            if number:sirens.append((re.sub(r'\D','',number.group(1)),page_no,line))
        scale=1
        if re.search(r'(?:en\s+milliers?\s+d[’\']?euros|in\s+(?:eur\s+)?thousands|en\s+keur|en\s+k€)',normal):scale=1000
        if re.search(r'(?:en\s+millions\s+d[’\']?euros|in\s+(?:eur\s+)?millions)',normal):scale=1000000
        foreign=bool(re.search(r'\b(?:usd|gbp|chf|jpy|cad|aud)\b|[$£]',normal))
        for index,line in enumerate(lines):
            norm=folded(line).strip()
            for key,patterns in LABELS.items():
                active_patterns=patterns
                if key=='total_assets' and re.search(r'bilan\s*[-–:]?\s*actif',normal) and not re.search(r'bilan\s*[-–:]?\s*passif',normal):
                    active_patterns=patterns+[r'total\s+general(?:\s*\([^)]*\))?']
                match=next((m for pattern in active_patterns if (m:=re.match(r'^'+pattern+r'(?=\s|:|\||\(|$)',norm))),None)
                if not match:continue
                suffix=norm[match.end():].strip()
                if suffix.startswith('(') and re.match(r'^\((?:i{1,3}|iv|v)\)',suffix):
                    suffix=re.sub(r'^\((?:i{1,3}|iv|v)\)\s*','',suffix)
                amounts=_columns(suffix)
                if not amounts and not suffix and index+1<len(lines):amounts=_columns(folded(lines[index+1]))
                if not amounts or foreign:continue
                headers=folded('\n'.join(lines[max(0,index-30):index]))
                # Never confuse gross/depreciation with net current-year assets.
                if key in ('total_assets','current_assets') and re.search(r'\bbrut\b|\bgross\b|amortissements|depreciation',headers):
                    if re.search(r'brut.*(?:amort|depreciation).*net',headers,re.S) and len(amounts)==3 and comparative_index(lines[max(0,index-30):index]) is None:
                        amount=amounts[2]
                    elif len(amounts)==4 and comparative_index(lines[max(0,index-30):index])==0:
                        amount=amounts[2]
                    else:
                        result.warnings.append('Asset columns are ambiguous (gross/net). Review the net current-year amount manually.');continue
                elif len(amounts)==1:
                    if comparative_index(lines[max(0,index-30):index]) is not None:
                        result.warnings.append('Comparative columns could not be identified. Review the current-year amounts manually.');continue
                    amount=amounts[0]
                elif len(amounts)==2:
                    column=comparative_index(lines[max(0,index-30):index])
                    if column is None:
                        result.warnings.append('Comparative columns could not be identified. Review the current-year amounts manually.');continue
                    amount=amounts[column]
                else:
                    result.warnings.append('Several accounting columns were detected. Review the affected fields manually.');continue
                if amount is not None:candidates[key].append((amount*scale,page_no,line,scale))
        if foreign:result.warnings.append('A non-EUR currency was detected. No amounts from that page were prefilled.')
    for key,items in candidates.items():
        distinct={x[0] for x in items}
        if len(distinct)==1:
            value,page,line,scale=items[0]
            if key in ('total_assets','current_assets','current_liabilities','total_liabilities') and value<0:
                result.warnings.append('A negative asset or liability amount was detected. Check the source; the affected field was left empty.');continue
            result.values[key]=value
            result.evidence[key]=dict(page=page,line=line[:300],scale=scale,method='labelled current-year amount')
        elif len(distinct)>1:
            result.warnings.append('Conflicting accounting values were detected. The affected fields were left empty.')
    for key,items in [('entity_name',entities),('buyer_siren',sirens)]:
        if len({x[0] for x in items})==1:
            value,page,line=items[0];result.fields[key]=value;result.evidence[key]=dict(page=page,line=line[:300])
        elif items:result.warnings.append('Several company identities were detected. Verify which entity owes the invoice.')
    if periods:
        end=max(x[1] for x in periods);matches=[x for x in periods if x[1]==end]
        if len({x[0] for x in matches})==1:
            result.fields.update(period_start=matches[0][0],period_end=end)
            result.evidence['period']=dict(page=matches[0][2],method='explicit accounting period')
    elif ends:
        end,page=max(ends)
        result.fields['period_end']=end
        if any(re.search(r'comptes\s+annuels|annual\s+(?:accounts|financial\s+statements)|duree[^\n]{0,25}\b12\s*mois',folded(page_text)) for page_text in pages):
            try:prior=end.replace(year=end.year-1)
            except ValueError:prior=end.replace(year=end.year-1,day=28)
            result.fields['period_start']=prior+timedelta(days=1)
            result.warnings.append('The annual start date was inferred from the closing date. Check the actual accounting period.')
        result.evidence['period']=dict(page=page,method='labelled year end; start may be inferred')
    # Derive non-equity liabilities only from explicit total assets and equity, never bank debt alone.
    if 'total_liabilities' not in result.values and all(k in result.values for k in ('total_assets','equity')):
        liability=result.values['total_assets']-result.values['equity']
        if liability>=0:
            result.values['total_liabilities']=liability
            result.evidence['total_liabilities']=dict(method='total assets minus book equity',inputs=['total_assets','equity'])
        else:result.warnings.append('A negative asset or liability amount was detected. Check the source; the affected field was left empty.')
    result.warnings=list(dict.fromkeys(result.warnings))
    return result


def extract_accounts(data):
    if not data or len(data)>5*1024*1024:raise ValueError('The annual statements PDF must be non-empty and no larger than 5 MB.')
    try:
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(data))
        if reader.is_encrypted or not 1<=len(reader.pages)<=300:raise ValueError()
        pages=[];warnings=[];ocr_count=0;used=False
        for index,page in enumerate(reader.pages[:MAX_PAGES]):
            text=page.extract_text(extraction_mode='layout') or ''
            if len(re.sub(r'\s','',text))<50 and ocr_count<MAX_OCR_PAGES:
                try:
                    with render_pdf_page(data,index) as image:text=ocr_image(image)
                    used=True;ocr_count+=1
                except ExtractionError as exc:warnings.append(str(exc));ocr_count+=1
            pages.append(text[:50000])
        if len(reader.pages)>MAX_PAGES:warnings.append('Only the first 16 pages were analysed. Review the remaining annual accounts manually.')
        if sum(len(re.sub(r'\s','',p))<50 for p in pages)>MAX_OCR_PAGES:warnings.append('OCR was limited to six pages. Complete unread fields manually.')
    except Exception as exc:
        raise ValueError('The annual statements must be a readable, unencrypted PDF (300 pages maximum).') from exc
    result=parse_account_pages(pages);result.warnings=list(dict.fromkeys(warnings+result.warnings));result.used_ocr=used
    return result


def apply_accounts_upload(state,prefix,data):
    digest=sha256(data).hexdigest()
    if state.get(prefix+'prefill_hash')==digest:return False
    try:result=extract_accounts(data)
    except ValueError as exc:result=AccountingExtraction(warnings=[str(exc)])
    mapping={'entity_name':'entity','buyer_siren':'siren','period_start':'start','period_end':'end'}
    for source,target in mapping.items():state[prefix+target]=result.fields.get(source,None if source.startswith('period_') else '')
    from financial_risk import FIELDS
    for name in FIELDS:state[prefix+name]=result.values.get(name)
    state[prefix+'reference']='; '.join('p. '+str(x) for x in sorted({v['page'] for v in result.evidence.values() if 'page' in v}))
    state[prefix+'reviewed']=False
    state[prefix+'prefill_hash']=digest
    state[prefix+'extraction']=dict(fields=result.fields,values=result.values,evidence=result.evidence,warnings=result.warnings,used_ocr=result.used_ocr)
    return True
