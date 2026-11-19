from datetime import date, timedelta
import json
import os
from copy import deepcopy
from pathlib import Path
import pandas as pd
import streamlit as st
from storage import InvoiceStore, StorageError
from i18n import Translator, localize_frame
from workspaces import WORKSPACES, overview
from invoice_extraction import FIELD_LABELS, apply_uploaded_invoice
from engine import seed, new_invoice, score, eligible, confirm, finance, quote, loss_scenario, settle, migrate_session, financing_checks, financing_blockers, complete_checks, journey, configure_interest, finance_with_risk_pricing
from future_value import continuous_future_value, investor_valuation, round_value, valuation_today
from pricing_ui import pricing_controls
st.set_page_config(page_title='InvoiceFlow · EN / FR', page_icon='↗', layout='wide')
language = st.sidebar.radio('Language / Langue', ['EN', 'FR'], horizontal=True, key='language')
t = Translator(language).text
st.markdown('<style>\n.block-container {padding-top:2rem; max-width:1400px}\n[data-testid="stSidebar"] {background:#13253c}\n[data-testid="stSidebar"] {color:#f2f6fb}\n[data-testid="stSidebar"] [data-testid="stMarkdownContainer"], [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {color:#f2f6fb}\n[data-testid="stSidebar"] [data-baseweb="select"] {background:#f5f7fb; border-radius:8px}\n[data-testid="stSidebar"] [data-baseweb="select"] * {color:#142239 !important; -webkit-text-fill-color:#142239 !important}\n[role="listbox"] {background:#f5f7fb; color:#142239}\n[role="option"] {color:#142239}\n[data-testid="stMetric"] {background:white; border:1px solid #e1e8ef; padding:20px; border-radius:16px}\n.hero {background:linear-gradient(120deg,#13253c,#164b53);color:white;padding:32px;border-radius:22px;margin-bottom:24px}\n.hero h1 {color:white;font-size:clamp(1.7rem,3vw,2.6rem);line-height:1.2;margin:0;overflow-wrap:break-word}.hero p {color:#d3e7e6;margin-bottom:0}\n.eyebrow {font-size:.8rem;letter-spacing:.16em;color:#87e3c7;margin-bottom:10px}\n</style>', unsafe_allow_html=True)
database = InvoiceStore(os.environ.get('INVOICEFLOW_DB_PATH', str(Path(__file__).parent / 'data' / 'invoiceflow.db')))
try:
    initial = st.session_state.get('invoices')
    if initial is None:
        initial = seed()
    migrate_session(initial)
    database.initialize(initial)
    invoices = database.load()
    st.session_state.invoices = invoices
except StorageError as exc:
    st.error(t(str(exc)))
    st.stop()

# Apply guided navigation before creating widgets for the new page.
route = st.session_state.pop('route_request', None)
if route:
    for key, value in route.items():
        st.session_state[key] = value


def navigate(role, target_page, invoice=None):
    route = {'ui_demo_role': role, 'ui_navigation': target_page}
    if invoice:
        if target_page == 'Buyer confirmation':
            route.update(ui_represented_buyer_simulation=invoice['buyer'], confirm_pick=invoice['id'])
        elif target_page == 'Financing':
            route['finance_pick'] = invoice['id']
        elif target_page == 'Invoice checks':
            route['checks_pick'] = invoice['id']
        elif target_page == 'Portfolio':
            route['portfolio_pick'] = invoice['id']
    st.session_state.route_request = route


def change_workspace():
    # Reset before navigation widgets are instantiated; explicit guided routes
    # still choose their destination through route_request above.
    st.session_state.ui_navigation = 'Overview'


def persist_update(invoice, operation, *args):
    candidate = deepcopy(invoice)
    operation(candidate, *args)
    database.update(candidate)
    st.session_state.focus_invoice = invoice['id']


def workflow(invoice):
    st.markdown('**' + t('Invoice progress') + '**')
    stages = journey(invoice)
    for column, (name, done) in zip(st.columns(5), stages):
        with column:
            st.markdown(('✅ ' if done else '○ ') + t(name))
    st.progress(sum(done for _, done in stages) / len(stages))
    st.caption(t('Current invoice: {reference}', reference=invoice['reference']))
    if invoice.get('outcome') == 'Paid':
        st.success(t('All steps completed. Payment has been simulated.'))
        return
    if invoice.get('financing'):
        role, target, label = 'Investor', 'Portfolio', 'Next: track payment'
    elif not invoice['identity'] or not invoice['documents']:
        role, target, label = 'SME', 'Invoice checks', 'Next: complete invoice checks'
    elif invoice['buyer_status'] != 'Confirmed':
        role, target, label = 'Buyer', 'Buyer confirmation', 'Next: buyer confirmation'
    else:
        role, target = 'Investor', 'Financing'
        label = 'Next: simulate financing' if eligible(invoice) else 'Review financing blockers'
    if page == target and profile == role:
        st.caption(t('Continue with the form and requirements below.'))
    else:
        st.button(t(label), key=f"next_{page}_{invoice['id']}", on_click=navigate,
                  args=(role, target, invoice), type='primary')


def show_requirements(invoice):
    if invoice.get('financing'):
        return
    blockers = financing_blockers(invoice)
    if not blockers:
        st.success(t('All requirements are met. This invoice is eligible for simulated financing.'))
    else:
        st.warning(t('Financing is blocked for the following reasons:'))
        for reason in blockers:
            st.write('• ' + t(reason))
    with st.expander(t('Financing requirements')):
        st.dataframe(pd.DataFrame([{t('Check'): t(label), t('Result'): t('Passed') if passed else t('To complete')}
                                   for label, passed, _ in financing_checks(invoice)]), hide_index=True,
                     use_container_width=True)


def selected_index(key, options):
    value = st.session_state.get(key)
    if key in st.session_state and value not in options:
        del st.session_state[key]
    return options.index(value) if value in options else 0

def euro(n):
    return f'{n:,.2f}'.replace(',', ' ').replace('.', ',') + ' €' if language == 'FR' else f'€{n:,.2f}'

def table(items):
    return localize_frame(pd.DataFrame([{'Reference': i['reference'], 'SME': i['seller'], 'Buyer': i['buyer'], 'Amount (€)': i['amount'], 'Due date': i['due'], 'Status': i['status'], 'Score /100': score(i)[0], 'Tracking': i['outcome'] or '—'} for i in items]), t)

def pick(items, key):
    return st.selectbox(t('Invoice'), [i['id'] for i in items], key=key, index=selected_index(key, [i['id'] for i in items]), format_func=lambda value: next((f"{i['reference']} · {i['seller']} · {euro(i['amount'])}" for i in items if i['id'] == value)))

def detail(i):
    workflow(i)
    show_requirements(i)
    a, b, c = st.columns(3)
    a.metric(t('Invoice amount'), euro(i['amount']))
    b.metric(t('Demo score'), f'{score(i)[0]} / 100')
    c.metric(t('Due date'), date.fromisoformat(i['due']).strftime('%d/%m/%Y' if language == 'FR' else '%d %b %Y'))
    with st.expander(t('Checks and audit trail')):
        st.dataframe(localize_frame(pd.DataFrame([{'Check': 'SME identity', 'Result': 'Declared verified (simulation)' if i['identity'] else 'Incomplete'}, {'Check': 'Invoice, purchase order, delivery', 'Result': 'Documents declared complete' if i['documents'] else 'Incomplete'}, {'Check': 'Buyer confirmation', 'Result': i['buyer_status']}, {'Check': 'Uniqueness within this workspace', 'Result': 'Supplier reference and file checked'}, {'Check': 'Demo risk assessment', 'Result': t('{p0}/100 · threshold 65', p0=score(i)[0])}]), t), hide_index=True, use_container_width=True)
        st.caption(t('No official checks, OCR or contact with a real buyer. The upload checkboxes are demo declarations.'))
        st.write(t('SHA-256 fingerprint of metadata'))
        st.code(i['record_hash'])
        if i['file_hash']:
            st.write(t('Uploaded file fingerprint'))
            st.code(i['file_hash'])
        st.caption(t('Database register, without blockchain. A fingerprint proves neither delivery of the service nor the absence of assignment on another platform.'))
        st.write(t('Score breakdown'))
        st.dataframe(localize_frame(pd.DataFrame([{'Criterion': k, 'Points': v} for k, v in score(i)[1].items()]), t), hide_index=True)
        st.caption(t('Maximum 100: financial strength 40/25/5; payment history 25/15/0; confirmation 25; documents 10. This score is not a probability of default.'))
    if i['note']:
        st.info(t(i['note']))


def future_value_panel(invoice):
    st.subheader(t('Investor future value'))
    funding = invoice['financing']
    missing = (not funding.get('financed_on') or 'annual_interest_rate' not in funding or
               (invoice.get('outcome') == 'Paid' and not funding.get('paid_on')))
    if missing:
        st.info(t('This older financing has no complete interest settings. Record its dates and annual rate to enable the calculation.'))
    if funding.get('pricing'):
        saved = funding['pricing']
        st.caption(t('Rate locked to the original risk-pricing report. No repricing is applied to an existing transaction.'))
        with st.expander(t('Saved risk-pricing assumptions')):
            st.json(saved)
    else:
        with st.expander(t('Interest simulation settings'), expanded=missing):
            with st.form('interest_settings_' + invoice['id']):
                start = st.date_input(t('Financing date'),
                                      value=date.fromisoformat(funding['financed_on']) if funding.get('financed_on') else valuation_today(),
                                      min_value=date.fromisoformat(invoice['issued']), max_value=valuation_today(),
                                      disabled=bool(funding.get('financed_on')), key='interest_start_' + invoice['id'])
                annual = st.number_input(t('Annual interest rate (%)'), min_value=0.0, max_value=100.0,
                                         value=float(funding.get('annual_interest_rate', 5.0)), step=0.1,
                                         key='interest_rate_' + invoice['id'])
                payment = None
                if invoice.get('outcome') == 'Paid' and not funding.get('paid_on'):
                    payment = st.date_input(t('Payment date'), value=valuation_today(),
                                            min_value=date.fromisoformat(invoice['issued']), max_value=valuation_today(),
                                            key='interest_paid_' + invoice['id'])
                save = st.form_submit_button(t('Save interest assumptions'))
            if save:
                try:
                    persist_update(invoice, configure_interest, annual, start, payment)
                    st.session_state.notice = t('Interest assumptions saved.')
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
    if missing:
        return
    as_of = valuation_today()
    if st.toggle(t('Choose a projection date'), key='future_projection_' + invoice['id']):
        as_of = st.date_input(t('Valuation date'), value=valuation_today(),
                              min_value=date.fromisoformat(funding['financed_on']),
                              key='future_date_' + invoice['id'])
    try:
        result = investor_valuation(invoice, as_of)
    except ValueError as exc:
        st.error(t(str(exc)))
        return
    a, b, c = st.columns(3)
    a.metric(t('Future value (simulation)'), euro(result['future_value']))
    b.metric(t('Theoretical interest'), euro(result['interest']))
    c.metric(t('Days without payment'), result['days'])
    st.caption(t('Capital advanced: {capital} · Annual interest: {rate}% · Time: {days}/365 = {years} years.',
                 capital=euro(result['principal']), rate=result['annual_rate'], days=result['days'],
                 years=f"{result['years']:.6f}"))
    st.caption(t('Calculated through {date}.', date=date.fromisoformat(result['end']).strftime('%d/%m/%Y')))
    st.latex(r'FV = P \times \exp\left(\frac{d}{365} \times \frac{r}{100}\right)')
    st.caption(t('The calculation starts on the financing date, including days before the invoice due date. It updates when this view is loaded or refreshed.'))
    st.caption(t('Separate theoretical scenario: not added to the invoice, fee, insurance indemnity or collected income. Repayment is not guaranteed.'))
    if result['stopped_at_payment']:
        st.info(t('Interest calculation stopped on the recorded payment date.'))

with st.sidebar:
    st.title(t('InvoiceFlow ↗'))
    st.caption(t('VERIFIED INVOICES. FASTER PAYMENTS.'))
    profile = st.selectbox(t('Demo role'), ['SME', 'Buyer', 'Investor'], key='ui_demo_role', format_func=t, index=selected_index('ui_demo_role', ['SME', 'Buyer', 'Investor']), on_change=change_workspace)
    workspace = WORKSPACES[profile]
    pages = workspace['pages']
    page = st.radio(t('Navigation'), pages, key='ui_navigation', format_func=t, index=selected_index('ui_navigation', pages))
    st.divider()
    st.caption(t('Educational prototype · NEOMA\n\nAll parties and transactions are fictional. No money is transferred.'))
    with st.expander(t('Reset demo')):
        reset = st.checkbox(t('Replace the shared demo data for all visitors'), key='ui_clear_the_data_in_this_session', value=st.session_state.get('ui_clear_the_data_in_this_session', False))
        if st.button(t('Reload examples'), disabled=not reset, key='ui_reload_examples'):
            try:
                database.reset(seed())
                st.session_state.pop('focus_invoice', None)
                st.session_state.pop('ui_filter_statuses', None)
                st.rerun()
            except StorageError as exc:
                st.error(t(str(exc)))
st.markdown('<div class="hero"><div class="eyebrow">' + t(workspace['title']) +
            '</div><h1>' + t(workspace['headline']) + '</h1><p>' +
            t(workspace['description']) + '</p></div>', unsafe_allow_html=True)
st.caption(t('{profile} workspace · Roles are interchangeable for the demo. Saved invoices are shared across visitors on this server; there is no authentication.', profile=t(profile)))
st.caption(t('Changes are saved automatically. Closing your browser does not delete saved invoices.'))
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))
if page == 'Overview':
    metrics, actionable = overview(profile, invoices)
    for column, (label, value, monetary) in zip(st.columns(3), metrics):
        column.metric(t(label), euro(value) if monetary else value)
    st.subheader(t(workspace['title']))
    st.button(t(workspace['action']), key='workspace_primary_action', on_click=navigate,
              args=(profile, workspace['target']), type='primary')
    for column, step in zip(st.columns(3), workspace['steps']):
        column.markdown('**' + t(step) + '**')
    st.subheader(t(workspace['section']))
    if actionable:
        st.dataframe(table(actionable), use_container_width=True, hide_index=True)
        st.subheader(t('Continue an invoice'))
        selected = pick(actionable, 'overview_pick')
        current = next(i for i in actionable if i['id'] == selected)
        workflow(current)
        show_requirements(current)
    else:
        st.info(t('No invoices in this workspace queue.'))
elif page == 'Upload an invoice':
    st.subheader(t('Unlock your cash flow'))
    focused = next((i for i in invoices if i['id'] == st.session_state.get('focus_invoice')), None)
    if focused:
        workflow(focused)
    if profile != 'SME':
        st.info(t('Select the SME role to upload an invoice.'))
    else:
        upload = st.file_uploader(t('Original invoice · PDF, PNG or JPEG · 10 MB max.'),
                                  type=['pdf', 'png', 'jpg', 'jpeg'],
                                  key='ui_original_invoice_pdf_png_or_jpeg_10_mb_max')
        st.caption(t('Optional: upload the invoice first to prefill its details. Changing the file replaces the detected fields.'))
        if upload is not None:
            with st.spinner(t('Reading the invoice…')):
                apply_uploaded_invoice(st.session_state, upload.getvalue(), upload.name)
            extraction = st.session_state.invoice_prefill
            if extraction['applied']:
                st.success(t('{count} fields prefilled. Review and correct them before submitting.',
                             count=len(extraction['applied'])))
            else:
                st.info(t('No reliable fields detected. You can complete the form manually.'))
            missing = [t(label) for name, label in FIELD_LABELS.items() if name not in extraction['applied']]
            if missing:
                st.caption(t('Complete manually: {fields}', fields=', '.join(missing)))
            if extraction['used_ocr']:
                st.caption(t('Text recognition was used. Check names, dates and amounts carefully.'))
            for warning in extraction['warnings']:
                st.warning(t(warning))
        else:
            # Removing a file keeps the user's draft but permits a fresh extraction on re-upload.
            st.session_state.pop('invoice_prefill_digest', None)
            st.session_state.pop('invoice_prefill', None)
        # Individual widgets commit draft edits on rerun, including language changes.
        # Business data is still saved only by the explicit submit button below.
        with st.container():
            a, b = st.columns(2)
            seller = a.text_input(t('SME name'), placeholder=t('E.g. Atelier Nova'), key='ui_sme_name', value=st.session_state.get('ui_sme_name', ''))
            siren = b.text_input(t('SIREN · 9-digit format'), max_chars=9, key='ui_siren_9_digit_format', value=st.session_state.get('ui_siren_9_digit_format', ''))
            buyer = a.text_input(t('Buyer'), placeholder=t('E.g. Groupe Horizon'), key='ui_buyer', value=st.session_state.get('ui_buyer', ''))
            reference = b.text_input(t('Invoice reference'), key='ui_invoice_reference', value=st.session_state.get('ui_invoice_reference', ''))
            amount = a.number_input(t('Invoice amount (€)'), min_value=1.0, value=st.session_state.get('ui_invoice_amount', 10000.0), step=100.0, key='ui_invoice_amount')
            issued = b.date_input(t('Issue date'), value=st.session_state.get('ui_issue_date', date.today()), max_value=date.today(), key='ui_issue_date')
            due = a.date_input(t('Due date'), value=st.session_state.get('ui_due_date', date.today() + timedelta(days=60)), min_value=date.today() + timedelta(days=1), key='ui_due_date')
            strength = b.selectbox(t('Declared buyer financial strength'), ['Strong', 'Average', 'Weak'], key='ui_declared_buyer_financial_strength', format_func=t, index=selected_index('ui_declared_buyer_financial_strength', ['Strong', 'Average', 'Weak']))
            history = a.selectbox(t('Declared payment history'), ['On time', 'Occasional delays', 'Frequent delays'], key='ui_declared_payment_history', format_func=t, index=selected_index('ui_declared_payment_history', ['On time', 'Occasional delays', 'Frequent delays']))
            st.caption(t('The detected details remain editable. Identity, supporting documents and buyer risk must be checked separately. Use fictional documents.'))
            identity = st.checkbox(t('Simulate verified SME identity'), key='ui_simulate_verified_sme_identity', value=st.session_state.get('ui_simulate_verified_sme_identity', False))
            documents = st.checkbox(t('Simulate complete documentation: invoice, purchase order and proof of delivery'), key='ui_simulate_complete_documentation_invoice_purchase_order_and_proof_of_delivery', value=st.session_state.get('ui_simulate_complete_documentation_invoice_purchase_order_and_proof_of_delivery', False))
            submitted = st.button(t('Submit invoice'), type='primary', key='ui_submit_invoice')
        if submitted:
            try:
                if amount is None or issued is None or due is None:
                    raise ValueError('Enter the invoice amount, issue date and due date before submitting.')
                item = new_invoice(invoices, seller=seller, siren=siren.strip(), buyer=buyer, reference=reference, amount=amount, issued=issued, due=due, documents=documents, identity=identity, strength=strength, history=history, file_bytes=upload.getvalue() if upload else b'', filename=upload.name if upload else '')
                database.add(item)
                st.session_state.focus_invoice = item['id']
                st.session_state.notice = t('Invoice {p0} submitted. Switch to the Buyer role to confirm it.', p0=item['reference'])
                st.rerun()
            except ValueError as exc:
                st.error(t(str(exc)))
elif page == 'Invoice checks':
    st.subheader(t('Complete an invoice file'))
    st.caption(t('These checks are simulated declarations. No official company or document verification is performed.'))
    if profile != 'SME':
        st.info(t('Select the SME role to complete invoice checks.'))
    else:
        editable = [i for i in invoices if not i.get('financing') and i['status'] != 'Closed']
        if not editable:
            st.info(t('No invoice files to complete.'))
        else:
            selected = pick(editable, 'checks_pick')
            i = next(i for i in editable if i['id'] == selected)
            detail(i)
            with st.form('complete_checks_' + i['id']):
                identity = st.checkbox(t('Simulate verified SME identity'), value=i['identity'], key='identity_' + i['id'])
                documents = st.checkbox(t('Simulate complete documentation: invoice, purchase order and proof of delivery'), value=i['documents'], key='documents_' + i['id'])
                save_checks = st.form_submit_button(t('Save invoice checks'), type='primary')
            if save_checks:
                try:
                    persist_update(i, complete_checks, identity, documents)
                    st.session_state.notice = t('Invoice checks saved.')
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
elif page == 'Buyer confirmation':
    st.subheader(t('Confirm your supplier invoices'))
    if profile != 'Buyer':
        st.info(t('Select the Buyer role to confirm or dispute an invoice.'))
    else:
        buyer = st.selectbox(t('Represented buyer (simulation)'), sorted({i['buyer'] for i in invoices}), key='ui_represented_buyer_simulation', index=selected_index('ui_represented_buyer_simulation', sorted({i['buyer'] for i in invoices})))
        items = [i for i in invoices if i['buyer'] == buyer and i['status'] not in ('Financed', 'Closed')]
        if not items:
            st.info(t('No invoices to process for this buyer.'))
        else:
            selected = pick(items, 'confirm_pick')
            i = next((i for i in items if i['id'] == selected))
            detail(i)
            with st.form('confirm'):
                decision = st.radio(t('Decision'), ['Confirm', 'Dispute'], horizontal=True, key='ui_decision', format_func=t, index=selected_index('ui_decision', ['Confirm', 'Dispute']))
                attestation = st.checkbox(t('I simulate confirmation of the service, amount and due date, and that the invoice is unpaid and undisputed.'), key='ui_i_simulate_confirmation_of_the_service_amount_and_due_date_and_that_the_invoice_is_unpaid_and_undisputed', value=st.session_state.get('ui_i_simulate_confirmation_of_the_service_amount_and_due_date_and_that_the_invoice_is_unpaid_and_undisputed', False))
                note = st.text_area(t('Comment · required for a dispute'), key='ui_comment_required_for_a_dispute', value=st.session_state.get('ui_comment_required_for_a_dispute', ''))
                submit = st.form_submit_button(t('Save decision'), type='primary')
            if submit:
                try:
                    if decision == 'Confirm' and (not attestation):
                        raise ValueError('Check the confirmation box to approve the invoice.')
                    persist_update(i, confirm, decision == 'Confirm', note)
                    st.session_state.notice = t('Decision saved.')
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
elif page == 'Financing':
    st.subheader(t('Finance confirmed invoices'))
    focused = next((i for i in invoices if i['id'] == st.session_state.get('focus_invoice')), None)
    if focused and focused.get('financing'):
        workflow(focused)
    if profile != 'Investor':
        st.info(t('Select the Investor role to simulate financing.'))
    else:
        items = [i for i in invoices if i['status'] not in ('Financed', 'Closed')]
        if not items:
            st.info(t('No invoices available.'))
        else:
            selected = pick(items, 'finance_pick')
            i = next((i for i in items if i['id'] == selected))
            detail(i)
            st.caption(t('Demo requirements: buyer confirmation, identity and documents declared verified, a future due date and a score ≥ 65/100.'))
            method = st.radio(t('Pricing method'), ['Risk-based pricing', 'Manual assumptions'],
                              format_func=t, key='ui_pricing_method')
            report = None
            recourse = st.toggle(t('With recourse to the SME'), value=st.session_state.get('ui_with_recourse_to_the_sme', False), key='ui_with_recourse_to_the_sme')
            coverage = st.slider(t('Hypothetical insolvency coverage (% of face value)'), 0, 100, st.session_state.get('ui_hypothetical_insolvency_coverage_of_face_value', 80), key='ui_hypothetical_insolvency_coverage_of_face_value')
            if method == 'Risk-based pricing':
                report = pricing_controls(i, t, euro)
                ready = bool(report and report['acceptable'])
            else:
                st.info(t('Manual demonstration: the fee and annual rate are independent assumptions, not a risk-based price.'))
                rate = st.slider(t('Fee on face value (%)'), 0.0, 10.0, st.session_state.get('ui_fee_on_face_value', 4.0), 0.1, key='ui_fee_on_face_value')
                annual_interest = st.number_input(t('Annual interest rate (%)'), min_value=0.0, max_value=100.0,
                                                  value=st.session_state.get('ui_financing_interest', 5.0), step=0.1,
                                                  key='ui_financing_interest')
                q = quote(i['amount'], rate)
                a, b = st.columns(2)
                a.metric(t('Simulated advance to the SME'), euro(q['advance']))
                b.metric(t('Gross margin if paid in full'), euro(q['fee']))
                days_to_due = max(0, (date.fromisoformat(i['due']) - valuation_today()).days)
                st.metric(t('Future value at due date (simulation)'),
                          euro(round_value(continuous_future_value(q['advance'], days_to_due / 365, annual_interest))))
                st.caption(t('Continuous interest uses the capital advanced and a separate annual percentage rate. The fee remains a one-off percentage of the invoice.'))
                ready = True
            st.caption(t('Before capital costs, insurance, losses and operating expenses. Coverage is hypothetical; no insurer is connected.'))
            if not eligible(i):
                st.warning(t('Resolve the requirements listed above before financing.'))
            if st.button(t('Simulate financing'), type='primary', disabled=not eligible(i) or not ready, key='ui_simulate_financing'):
                try:
                    if method == 'Risk-based pricing':
                        persist_update(i, finance_with_risk_pricing, report['assumptions'], recourse, coverage)
                    else:
                        persist_update(i, finance, rate, recourse, coverage, annual_interest)
                    st.session_state.notice = t('Simulated financing saved to the portfolio.')
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
elif page == 'Simulator':
    st.subheader(t('Explore financing scenarios'))
    a, b = st.columns(2)
    amount = a.number_input(t('Invoice (€)'), min_value=1.0, value=st.session_state.get('ui_invoice', 10000.0), step=100.0, key='ui_invoice')
    rate = b.slider(t('Fee (%)'), 0.0, 10.0, st.session_state.get('ui_fee', 4.0), 0.1, key='ui_fee')
    coverage = a.slider(t('Hypothetical insolvency coverage (%)'), 0, 100, st.session_state.get('ui_hypothetical_insolvency_coverage', 80), key='ui_hypothetical_insolvency_coverage')
    recourse = b.toggle(t('With recourse'), value=st.session_state.get('ui_with_recourse', False), key='ui_with_recourse')
    result = loss_scenario(amount, rate, coverage, recourse)
    x, y, z = st.columns(3)
    x.metric(t('Immediate advance'), euro(result['advance']))
    y.metric(t('Gross fee'), euro(result['fee']))
    z.metric(t('Capital at risk after insurance'), euro(result['residual']))
    st.dataframe(localize_frame(pd.DataFrame([{'Scenario': 'Full payment', 'Model outcome': t('{p0} received; gross margin {p1}.', p0=euro(amount), p1=euro(result['fee']))}, {'Scenario': 'Late payment', 'Model outcome': 'No final loss calculated; financing period extended.'}, {'Scenario': 'Covered insolvency', 'Model outcome': t('Hypothetical indemnity {p0} ; residual capital {p1}.', p0=euro(result['indemnity']), p1=euro(result['residual']))}, {'Scenario': 'Dispute / fraud', 'Model outcome': 'No coverage assumed; exposure may reach the full advance.'}]), t), hide_index=True, use_container_width=True)
    if recourse:
        st.info(t('Recourse assumption: a claim against the SME for {p0} after indemnification. Recovery remains uncertain; the exposure is not eliminated.', p0=euro(result['supplier_claim'])))
    st.caption(t('Simplified assumptions: coverage applied to face value, indemnity capped at the advance; no recoveries, deductibles, delays or costs included. Non-recourse does not mean protection against every fraud or dispute.'))
    st.subheader(t('Investor future value'))
    annual = st.number_input(t('Annual interest rate (%)'), min_value=0.0, max_value=100.0,
                             value=st.session_state.get('ui_simulation_interest', 5.0), step=0.1,
                             key='ui_simulation_interest')
    years = st.number_input(t('Time without payment (years)'), min_value=0.0, max_value=100.0,
                            value=st.session_state.get('ui_simulation_years', 1.0), step=0.01,
                            key='ui_simulation_years')
    future = continuous_future_value(result['advance'], years, annual)
    a, b = st.columns(2)
    a.metric(t('Future value (simulation)'), euro(round_value(future)))
    b.metric(t('Theoretical interest'), euro(round_value(future - result['advance'])))
    st.latex(r'FV = P \times \exp\left(t \times \frac{r}{100}\right)')
    st.caption(t('Capital is the simulated advance. Enter the annual rate as a percentage: 5 means 5%, not 0.05%.'))
    st.caption(t('Separate theoretical scenario: not added to the invoice, fee, insurance indemnity or collected income. Repayment is not guaranteed.'))
    st.subheader(t('Revenue simulation'))
    count = st.number_input(t('Invoices financed per month'), min_value=1, value=st.session_state.get('ui_invoices_financed_per_month', 100), step=1, key='ui_invoices_financed_per_month')
    a, b = st.columns(2)
    a.metric(t('Hypothetical monthly fee revenue'), euro(count * result['fee']))
    b.metric(t('Hypothetical annual fee revenue'), euro(count * result['fee'] * 12))
    st.caption(t('At constant volume, before all expenses. This simulation is not a business forecast.'))
elif page == 'Portfolio':
    st.subheader(t('Invoice and transaction tracking'))
    filter_options = sorted({i['status'] for i in invoices})
    previous_filter = st.session_state.get('ui_filter_statuses', [])
    valid_filter = [status for status in previous_filter if status in filter_options]
    if valid_filter != previous_filter:
        st.session_state.ui_filter_statuses = valid_filter
    statuses = st.multiselect(t('Filter statuses'), filter_options, key='ui_filter_statuses', format_func=t, default=valid_filter)
    items = [i for i in invoices if not statuses or i['status'] in statuses]
    st.dataframe(table(items), hide_index=True, use_container_width=True)
    st.download_button(t('Export view as CSV'), table(items).to_csv(index=False).encode('utf-8-sig'), 'invoiceflow_invoices.csv', 'text/csv')
    st.download_button(t('Export saved invoices as JSON'), json.dumps(invoices, ensure_ascii=False, indent=2), 'invoiceflow_session.json', 'application/json')
    if invoices:
        selected = pick(invoices, 'portfolio_pick')
        i = next((i for i in invoices if i['id'] == selected))
        detail(i)
        f = i['financing']
        if f:
            st.write(t('Advance: **{p0}** · Fee: **{p1} %** · Hypothetical coverage: **{p2} %** · {p3}', p0=euro(f['advance']), p1=f"{f['rate']:.4f}", p2=f['coverage'], p3=t('With recourse' if f['recourse'] else 'Without recourse')))
            if profile == 'Investor':
                future_value_panel(i)
            if i['outcome'] == 'Insolvency':
                r = loss_scenario(i['amount'], f['rate'], f['coverage'], f['recourse'])
                st.warning(t('Insolvency scenario: hypothetical indemnity {p0}, remaining capital at risk {p1}. No real payment.', p0=euro(r['indemnity']), p1=euro(r['residual'])))
            elif i['outcome'] == 'Dispute':
                st.warning(t('Dispute: no indemnity assumed. Capital at risk: {p0}.', p0=euro(f['advance'])))
            elif i['outcome'] == 'Late payment':
                st.info(t('Payment pending. No collected revenue or automatic indemnity assumed.'))
            elif i['outcome'] == 'Paid':
                st.success(t('Full payment simulated. Gross discount before costs: {p0}.' if f.get('pricing') else 'Full payment simulated. Hypothetical gross margin: {p0}.', p0=euro(f['fee'])))
            if profile == 'Investor' and i['status'] == 'Financed':
                with st.form('settle'):
                    outcome = st.selectbox(t('Event to simulate'), ['Paid', 'Late payment', 'Insolvency', 'Dispute'], key='ui_event_to_simulate', format_func=t, index=selected_index('ui_event_to_simulate', ['Paid', 'Late payment', 'Insolvency', 'Dispute']))
                    if st.form_submit_button(t('Save tracking update')):
                        try:
                            persist_update(i, settle, outcome)
                            st.session_state.notice = t('Tracking updated.')
                            st.rerun()
                        except ValueError as exc:
                            st.error(t(str(exc)))
st.divider()
st.caption(t('InvoiceFlow · Academic demo based on your concept. Confirmation, scoring, insurance and financing are simulated; no banking service, external register or blockchain is connected.'))

