"""SME-facing signature invitation, without a buyer workspace or signing-link exposure."""
import hmac
import os
import streamlit as st
from electronic_signature import (YousignClient, SignatureError, confirmation_pdf,
                                  send_signature, refresh_signature, download_evidence)


def setting(key, default=''):
    value = os.environ.get(key)
    if value is not None:
        return value
    try:
        return str(st.secrets.get(key, default))
    except (FileNotFoundError, KeyError):
        return default


def render_signature(invoice, database, t):
    st.subheader(t('Request the buyer signature'))
    st.caption(t('The buyer receives an email and signs a confirmation attestation outside InvoiceFlow. No buyer account is needed.'))
    st.caption(t('The attestation contains the invoice details and a declaration about the service, amount, due date and absence of payment or dispute. It is separate from the original invoice.'))
    environment = setting('YOUSIGN_ENVIRONMENT', 'sandbox')
    api_key = setting('YOUSIGN_API_KEY')
    access_code = setting('SIGNATURE_SEND_CODE')
    configured = bool(api_key and len(access_code) >= 12)
    if environment == 'sandbox':
        st.info(t('Test mode: signatures have no legal effect. Trial accounts may only email members of the Yousign organisation.'))
    else:
        st.caption(t('Simple electronic signature with an email verification code. This does not verify identity or authority to represent the buyer.'))
    if not configured:
        st.warning(t('Electronic signature is not configured. No invitation can be sent yet.'))
        with st.expander(t('Signature service setup')):
            st.write(t('In Streamlit secrets, add a Yousign API key, choose sandbox or production, and set a sending access code of at least 12 characters. Never paste the API key into this page.'))
            st.code('YOUSIGN_API_KEY = "..."\nYOUSIGN_ENVIRONMENT = "sandbox"\nSIGNATURE_SEND_CODE = "..."', language='toml')
    # This shared demo has no user accounts: protect all provider operations with an operator code.
    authorised = False
    if configured:
        entered = st.text_input(t('Signature access code'), type='password', key='signature_access_code')
        authorised = hmac.compare_digest(entered.encode(), access_code.encode())
        if entered and not authorised:
            st.error(t('Invalid signature access code.'))
    record = invoice.get('signature')
    if record:
        st.write(t('Signature status') + ' : **' + t(record['state']) + '**')
        st.write(t('Recipient') + ' : ' + record['contact']['email'])
        if record['environment'] == 'sandbox':
            st.caption(t('This request belongs to the test environment. It is not a legally binding signature.'))
        if record['state'] in ('needs_review', 'creating', 'draft'):
            st.warning(t('Sending is incomplete or uncertain. Check the Yousign dashboard before any new invitation. This app blocks duplicate sends.'))
        if st.button(t('Check signature status'), disabled=not authorised or not record.get('request_id'),
                     key='signature_refresh_' + invoice['id']):
            try:
                with st.spinner(t('Checking the signature service…')):
                    refresh_signature(database, invoice['id'], YousignClient(api_key, environment))
                st.rerun()
            except ValueError as exc:
                st.error(t(str(exc)))
        if record['state'] == 'done' and authorised:
            if st.button(t('Retrieve signed documents'), key='signature_evidence_' + invoice['id']):
                try:
                    client = YousignClient(api_key, environment)
                    st.download_button(t('Download signed attestation'), download_evidence(invoice, client),
                                       file_name='signed-confirmation.pdf', mime='application/pdf')
                    st.download_button(t('Download signature audit trail'), download_evidence(invoice, client, audit=True),
                                       file_name='signature-audit-trails.zip', mime='application/zip')
                except ValueError as exc:
                    st.error(t(str(exc)))
        return
    if invoice['buyer_status'] == 'Confirmed':
        st.info(t('This invoice is already confirmed. Existing confirmations have been preserved.'))
        return
    with st.form('signature_form_' + invoice['id']):
        email = st.text_input(t('Buyer email address'), value=invoice.get('buyer_email', ''), key='signature_email_' + invoice['id'])
        a, b = st.columns(2)
        first = a.text_input(t('Signer first name'), key='signature_first_' + invoice['id'], max_chars=80)
        last = b.text_input(t('Signer last name'), key='signature_last_' + invoice['id'], max_chars=80)
        consent = st.checkbox(t('I have checked the recipient and want to send this invoice confirmation for signature.'),
                              key='signature_consent_' + invoice['id'])
        send = st.form_submit_button(t('Send signature invitation'), type='primary', disabled=not authorised)
    if send:
        try:
            if not consent:
                raise SignatureError('Check the recipient confirmation box before sending.')
            with st.spinner(t('Sending the signature invitation…')):
                send_signature(database, invoice['id'], YousignClient(api_key, environment),
                               dict(first_name=first, last_name=last, email=email))
            st.session_state.notice = t('The signature service accepted the invitation. The invoice remains unconfirmed until the signature is checked.')
            st.rerun()
        except ValueError as exc:
            st.error(t(str(exc)))
    if first.strip() and last.strip() and email.strip():
        st.download_button(t('Preview the attestation to sign'),
                           confirmation_pdf(invoice, dict(first_name=first, last_name=last, email=email), environment),
                           file_name='confirmation-preview.pdf', mime='application/pdf',
                           key='signature_preview_' + invoice['id'])
