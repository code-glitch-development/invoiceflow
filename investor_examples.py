"""Five isolated investor examples. Never inserted into the invoice database."""
from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO

from future_value import valuation_today


def accounts_pdf(company, siren, year, values):
    """Small, text-readable source PDF for the explicitly illustrative inputs."""
    labels = {'total_assets': 'Total actif', 'current_assets': 'Actif circulant net',
              'current_liabilities': "Dettes a moins d'un an",
              'total_liabilities': 'Total passif hors capitaux propres',
              'equity': 'Capitaux propres', 'retained_earnings': 'Benefices accumules non distribues',
              'ebit': 'EBIT'}
    lines = ['EXAMPLE ANNUAL ACCOUNTS - ILLUSTRATIVE DATA', 'Comptes annuels',
             'Denomination sociale : ' + company, 'SIREN : ' + siren,
             f'Exercice du 01/01/{year} au 31/12/{year}', 'Montants en euros']
    lines += [f'{labels[k]} : {v:.2f}' for k, v in values.items()]
    lines += ['Prepared solely for the separate investor example catalogue.']
    def escape(s):
        return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream = ('BT /F1 11 Tf 45 790 Td 20 TL ' + ' T* '.join('('+escape(s)+') Tj' for s in lines) + ' ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    out = BytesIO(); out.write(b'%PDF-1.4\n'); offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell()); out.write(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start = out.tell(); out.write(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: out.write(f'{offset:010d} 00000 n \n'.encode())
    out.write(f'trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return out.getvalue()


def investor_examples(today=None):
    today = today or valuation_today()
    # TA, CA, CL, total non-equity liabilities, equity, accumulated profits, EBIT.
    cases = [
        ('Atelier Nova Conseil SAS', '123456789', 'Lumen Services SAS', 12000, 30,
         (1000000,600000,300000,600000,400000,200000,80000)),
        ('Orbe Digital SAS', '234567890', 'Sillage Operations SAS', 9000, 45,
         (800000,360000,280000,560000,240000,80000,50000)),
        ('Studio Prisme SAS', '345678901', 'Meridien Services SAS', 18000, 60,
         (1000000,400000,350000,800000,200000,100000,50000)),
        ('Nacre Digital SAS', '456789012', 'Cobalt Solutions SAS', 6500, 75,
         (1000000,300000,300000,900000,100000,0,100000)),
        ('Boreal IT SAS', '567890123', 'Solstice Distribution SAS', 14000, 90, None),
    ]
    fields = ('total_assets','current_assets','current_liabilities','total_liabilities','equity','retained_earnings','ebit')
    result = []
    for index, (seller, siren, buyer, amount, days, numbers) in enumerate(cases, 1):
        identifier = f'EXAMPLE-INV-{index:02d}'
        invoice = dict(id=identifier, key=identifier, reference=identifier, seller=seller, siren=siren,
            buyer=buyer, amount=amount, issued=today.isoformat(), due=(today+timedelta(days=days)).isoformat(),
            identity=False, documents=False, buyer_status='Confirmed', status='Approved',
            financing=None, outcome=None, file_hash='', record_hash='', note='', investor_example=True)
        source = None
        if numbers:
            values = dict(zip(fields, numbers)); year = today.year-1
            buyer_siren = f'98000000{index}'
            source = accounts_pdf(buyer, buyer_siren, year, values)
            invoice['buyer_accounts'] = dict(entity_name=buyer, buyer_siren=buyer_siren,
                company_type='non_financial_non_manufacturing', period_start=date(year,1,1).isoformat(),
                period_end=date(year,12,31).isoformat(), values=values,
                source_reference='Illustrative accounts, page 1; not uploaded company data',
                document=dict(filename=identifier+'-accounts.pdf',sha256=sha256(source).hexdigest()))
        result.append(dict(invoice=invoice, accounts_pdf=source))
    return result


def render_investor_examples(t, euro):
    import streamlit as st
    from altman_tariff import tariff_quote
    from engine import finance_with_altman_tariff
    from financial_risk import assess_buyer
    from commission_ui import render_commission_breakdown
    st.subheader(t('Example invoices') + ' · 5')
    st.caption(t('Separate example catalogue. These five cases are not uploaded invoices and never enter SME/buyer records or your saved portfolio.'))
    today = valuation_today()
    if st.session_state.get('example_catalogue_date') != today.isoformat():
        st.session_state.investor_example_cases = investor_examples(today)
        st.session_state.example_catalogue_date = today.isoformat()
    columns = st.columns(3)
    for index, case in enumerate(st.session_state.investor_example_cases):
        invoice = case['invoice']; report = tariff_quote(invoice, today); risk = assess_buyer(invoice, today)
        with columns[index % 3], st.container(border=True):
            st.caption(t('Example') + ' · ' + invoice['reference'])
            st.markdown('**' + invoice['seller'] + '**')
            st.write(t('Buyer') + ' · ' + invoice['buyer'])
            st.metric(t('Example invoice amount'), euro(invoice['amount']))
            st.write(t('Buyer accounting risk') + ' · **' + t(risk['band']) + '**')
            st.write('Z″ · **' + (f"{risk['value']:.4f}" if risk['value'] is not None else t('Risk not assessed')) + '**')
            st.write(t('Annual continuous tariff') + f" · **{report['policy_annual_rate_percent']:.0f} %**")
            st.caption(t('{days} days', days=report['horizon_days']))
            with st.expander(t('Example calculation details')):
                render_commission_breakdown(invoice['amount'], report, t, euro)
                if case['accounts_pdf']:
                    st.download_button(t('Download example annual accounts'), case['accounts_pdf'],
                        invoice['buyer_accounts']['document']['filename'], 'application/pdf', key='example_pdf_'+invoice['id'])
                st.json(report)
            if invoice.get('financing'):
                st.success(t('Example simulation completed. Your saved portfolio is unchanged.'))
            else:
                for reason in report['blockers']: st.info(t(reason))
                if st.button(t('Simulate this example'), key='example_finance_'+invoice['id'], disabled=not report['acceptable']):
                    finance_with_altman_tariff(invoice)
                    st.rerun()
