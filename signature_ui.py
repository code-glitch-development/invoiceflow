"""Optional automatic email, manual drafts and a dedicated buyer response page."""
import os
import streamlit as st
from buyer_confirmation import (ConfirmationError, create_invitation, email_draft,
                                inspect_invitation, respond)


def mail_setting(name, default=''):
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, KeyError):
        return default


def render_confirmation(invoice, database, t, language):
    from transactional_mail import BrevoClient, send_confirmation_email
    st.subheader(t('Request buyer confirmation'))
    st.caption(t('Send the personal confirmation link directly from InvoiceFlow, or prepare an email for your own mailbox.'))
    st.caption(t('This is a confirmation by link. It does not independently verify the recipient identity or authority to represent the buyer.'))
    record = invoice.get('buyer_confirmation')
    if record:
        st.write(t('Confirmation status') + ' : **' + t(record['status']) + '**')
        st.write(t('Recipient') + ' : ' + record['email'])
        if record['status'] != 'pending':
            st.write(t('Response recorded on {date} by {name}', date=record['responded_at'], name=record['respondent_name']))
            if record.get('note'):
                st.text(record['note'])
            return
        st.caption(t('Link expires on {date}', date=record['expires_at']))
    elif invoice['buyer_status'] == 'Confirmed':
        st.info(t('This invoice is already confirmed. Existing confirmations have been preserved.'))
        return
    api_key = mail_setting('BREVO_API_KEY')
    sender = mail_setting('BREVO_SENDER_EMAIL')
    configured = bool(api_key and sender)
    if not configured:
        st.warning(t('Automatic email is not configured yet. No email will be sent by InvoiceFlow until setup is complete.'))
        with st.expander(t('Set up free automatic email')):
            st.write(t('Create a Brevo Free account, validate your sender and activate transactional sending. Add these values in Streamlit Settings → Secrets. No software installation is needed.'))
            st.code('BREVO_API_KEY = "..."\nBREVO_SENDER_EMAIL = "your-verified-address@example.com"', language='toml')
            st.caption(t('Keep the API key private.'))
    delivery = record.get('email_delivery', {}) if record else {}
    state = delivery.get('state')
    if state == 'accepted':
        st.success(t('The mail service accepted the email for sending to {email}. This does not confirm inbox delivery; check spam and Brevo logs if needed.', email=record['email']))
    elif state in ('sending', 'unknown'):
        st.warning(t('Email sending is pending or uncertain. Check Brevo transactional logs before sending again.'))
    elif state == 'rejected':
        st.error(t('The mail service rejected the last email. Check the sender, account and API configuration before trying again.'))
    default_url = mail_setting('INVOICEFLOW_PUBLIC_URL') or getattr(getattr(st, 'context', None), 'url', '') or ''
    with st.form('confirmation_form_' + invoice['id']):
        email = st.text_input(t('Buyer email address'), value=invoice.get('buyer_email', ''), key='confirmation_email_' + invoice['id'])
        address = st.text_input(t('Public address of this app'), value=default_url,
                                placeholder='https://your-app.streamlit.app/', key='confirmation_app_url_' + invoice['id'])
        st.caption(t('Use the address shown in your browser. The buyer must be able to open this app.'))
        replace = st.checkbox(t('Replace the previous link (it will stop working).'), key='confirmation_replace_' + invoice['id']) if record else False
        auto = st.form_submit_button(t('Send confirmation email'), type='primary', disabled=not configured or state in ('sending', 'unknown'))
        prepare = st.form_submit_button(t('Prepare confirmation email'), disabled=state in ('sending', 'unknown'))
    if auto or prepare:
        try:
            client = None
            if auto:
                client = BrevoClient(api_key, sender, mail_setting('BREVO_SENDER_NAME', 'InvoiceFlow'))
            invitation = create_invitation(database, invoice['id'], email, address, replace=replace)
            st.session_state['confirmation_draft_' + invoice['id']] = invitation
            if auto:
                with st.spinner(t('Sending the confirmation email…')):
                    send_confirmation_email(database, invoice['id'], invitation, client,
                                            language=language)
            st.rerun()
        except ValueError as exc:
            st.error(t(str(exc)))
    draft = st.session_state.get('confirmation_draft_' + invoice['id'])
    if draft and record and draft['token_hash'] == record['token_hash']:
        message = email_draft(invoice, draft, language)
        if state not in ('accepted', 'sending', 'unknown'):
            st.info(t('A link is prepared, but InvoiceFlow has not sent an email. Use automatic sending below or open your own email app.'))
            if st.button(t('Send this email automatically'), type='primary', disabled=not configured,
                         key='mail_send_existing_' + invoice['id']):
                try:
                    with st.spinner(t('Sending the confirmation email…')):
                        send_confirmation_email(database, invoice['id'], draft,
                            BrevoClient(api_key, sender, mail_setting('BREVO_SENDER_NAME', 'InvoiceFlow')),
                            language=language)
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
            st.link_button(t('Open my email app'), message['mailto'])
        with st.expander(t('Copy the link or email text')):
            st.caption(t('If your email app does not open, paste this message into your usual webmail.'))
            st.code(draft['link'], language=None)
            st.text(message['subject'])
            st.code(message['body'], language=None)
    elif record:
        st.info(t('The existing link remains valid until expiry or response. To prepare a new email here, explicitly replace the previous link.'))
    st.button(t('Refresh buyer response'), key='confirmation_refresh_' + invoice['id'])


def render_recipient(database, token, t, euro):
    """This path stops the main app before any role menu, portfolio or export is rendered."""
    st.title(t('Invoice confirmation'))
    try:
        invoice = inspect_invitation(database, token)
    except ValueError as exc:
        st.error(t(str(exc)))
        return
    record = invoice['buyer_confirmation']
    if record['status'] != 'pending':
        st.success(t('Your response has been recorded. You can close this page.'))
        st.write(t('Confirmation status') + ' : **' + t(record['status']) + '**')
        st.caption(t('Response recorded on {date} by {name}', date=record['responded_at'], name=record['respondent_name']))
        return
    st.write(t('Please review this invoice before responding.'))
    for label, value in [('SME', invoice['seller']), ('Buyer', invoice['buyer']),
                         ('Invoice reference', invoice['reference']), ('Invoice amount', euro(invoice['amount'])),
                         ('Issue date', invoice['issued']), ('Due date', invoice['due'])]:
        st.text(t(label) + ' : ' + str(value))
    st.caption(t('Requested recipient: {email}', email=record['email']))
    st.caption(t('You are confirming the displayed invoice details. The original uploaded document is not available on this page.'))
    with st.form('buyer_link_response'):
        name = st.text_input(t('Your full name'), max_chars=160, key='buyer_response_name')
        decision = st.radio(t('Decision'), ['Confirm', 'Dispute'], format_func=t, horizontal=True, key='buyer_response_decision')
        attestation = st.checkbox(t('I declare that I am authorised to represent the buyer and confirm the service, amount, due date, and that this invoice is unpaid and undisputed.'), key='buyer_response_attestation')
        note = st.text_area(t('Comment · required for a dispute'), max_chars=2000, key='buyer_response_note')
        submit = st.form_submit_button(t('Submit my response'), type='primary')
    st.caption(t('This is a confirmation by personal link, without independent identity verification. It is not a certified electronic signature or a payment guarantee.'))
    if submit:
        try:
            respond(database, token, approved=decision == 'Confirm', name=name, attestation=attestation, note=note)
            st.rerun()
        except ValueError as exc:
            st.error(t(str(exc)))
