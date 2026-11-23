"""Buyer demo workspace: company filtering and atomic, explicitly simulated replies."""
from datetime import datetime, timezone
import json
from engine import canonical, confirm
from buyer_confirmation import ConfirmationError


def buyer_invoices(invoices, company):
    return [i for i in invoices if canonical(i['buyer']) == canonical(company)] if company else []


def respond_in_workspace(store, invoice, company, *, approved, name, attestation=False, note=''):
    """This is a demo declaration, never an authenticated buyer signature."""
    name, note = name.strip(), note.strip()
    if not name or len(name) > 160:
        raise ConfirmationError('Enter your full name (160 characters maximum).')
    if not isinstance(approved, bool):
        raise ConfirmationError('Choose a confirmation decision.')
    if approved and not attestation:
        raise ConfirmationError('Check the declaration before confirming this invoice.')
    if not approved and not note:
        raise ConfirmationError('Provide a reason for the dispute.')
    if len(note) > 2000:
        raise ConfirmationError('The comment must contain at most 2000 characters.')
    with store.transaction() as db:
        row = db.execute('SELECT payload, version FROM invoices WHERE id = ?', (invoice['id'],)).fetchone()
        if row is None or row[1] != invoice.get('_version'):
            raise ConfirmationError('This invoice changed in another session. Reload the latest data before trying again.')
        current = json.loads(row[0])
        if not company or canonical(current['buyer']) != canonical(company):
            raise ConfirmationError('Select the buyer company named on this invoice.')
        old = current.get('buyer_confirmation', {})
        if old.get('status', 'pending') != 'pending' or current['buyer_status'] != 'Pending':
            raise ConfirmationError('The buyer has already responded. Their decision cannot be overwritten.')
        if current.get('financing') or current['status'] in ('Financed', 'Closed'):
            raise ConfirmationError('A financed or closed invoice cannot be changed.')
        confirm(current, approved, note)
        moment = datetime.now(timezone.utc).isoformat()
        current['buyer_confirmation'] = dict(old, status='confirmed' if approved else 'disputed',
            email=old.get('email', current.get('buyer_email', '')), responded_at=moment,
            respondent_name=name, attestation=approved and attestation, note=note,
            method='buyer_workspace_demo', identity_verified=False)
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(current), current['id']))


def render_buyer_confirmation(invoice, store, company, t, euro):
    import streamlit as st
    st.subheader(t('Review an invoice as the buyer'))
    st.warning(t('Demo workspace: selecting a company does not authenticate you or verify your authority to represent it.'))
    st.write(t('Supplier') + ' · **' + invoice['seller'] + '**')
    a, b = st.columns(2)
    a.metric(t('Invoice amount'), euro(invoice['amount']))
    b.metric(t('Due date'), invoice['due'])
    st.write(t('Invoice reference') + ' · ' + invoice['reference'])
    record = invoice.get('buyer_confirmation', {})
    if invoice['buyer_status'] != 'Pending' or record.get('status', 'pending') != 'pending':
        st.info(t('This invoice already has a buyer decision. The recorded response is read-only.'))
        st.write(t('Buyer confirmation') + ' · **' + t(invoice['buyer_status']) + '**')
        if record.get('responded_at'):
            st.caption(t('Response recorded on {date} by {name}', date=record['responded_at'], name=record['respondent_name']))
        if record.get('note'):
            st.text(record['note'])
        return
    if invoice.get('financing') or invoice['status'] in ('Financed', 'Closed'):
        st.info(t('Historical financed operations are read-only. Their original amounts and pricing assumptions are preserved.'))
        return
    prefix = 'buyer_reply_' + invoice['id'] + '_'
    with st.form(prefix + 'form'):
        name = st.text_input(t('Your full name'), key=prefix+'name')
        decision = st.radio(t('Buyer decision'), ['Confirm invoice', 'Dispute invoice'], format_func=t, key=prefix+'decision')
        attestation = st.checkbox(t('I confirm that this invoice is accepted and payable by the selected buyer company.'), key=prefix+'attestation')
        note = st.text_area(t('Comment / reason for dispute'), max_chars=2000, key=prefix+'note')
        submitted = st.form_submit_button(t('Save buyer decision (demo)'), type='primary')
    if submitted:
        try:
            respond_in_workspace(store, invoice, company, approved=decision=='Confirm invoice',
                                 name=name, attestation=attestation, note=note)
            st.session_state.notice = t('Buyer decision recorded as a demo declaration. Identity and supporting-document checks remain separate.')
            st.rerun()
        except ValueError as exc:
            st.error(t(str(exc)))
