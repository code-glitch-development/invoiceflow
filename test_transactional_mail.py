"""Mail sends are mocked: tests never contact Brevo or send an email."""
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from buyer_confirmation import ConfirmationError, create_invitation, respond
import unittest
import test_buyer_confirmation as fixtures
from transactional_mail import BrevoClient, MailError, send_confirmation_email


class MailSendingTests(unittest.TestCase):
    setUp = fixtures.ConfirmationTests.setUp
    invitation = fixtures.ConfirmationTests.invitation
    def send(self, draft, client=None):
        client = client or Mock(send=Mock(return_value='<message-id@example.com>'))
        return send_confirmation_email(self.store, self.invoice['id'], draft, client,
            now=self.now)

    def test_api_acceptance_is_saved_without_confirming_invoice(self):
        draft=self.invitation()
        client=Mock(send=Mock(return_value='<message-id@example.com>'))
        self.send(draft,client)
        invoice=self.store.load()[0]
        self.assertEqual(invoice['buyer_status'],'Pending')
        delivery=invoice['buyer_confirmation']['email_delivery']
        self.assertEqual(delivery['state'],'accepted')
        self.assertEqual(delivery['message_id'],'<message-id@example.com>')
        self.assertNotIn(draft['token'],json.dumps(invoice))
        self.assertEqual(client.send.call_args.args[0],'buyer@example.com')
        self.assertIn(draft['link'],client.send.call_args.args[1]['body'])

    def test_duplicate_sends_block_before_network(self):
        draft=self.invitation();client=Mock(send=Mock(return_value='id'))
        self.send(draft,client)
        with self.assertRaises(MailError): self.send(draft,client)
        self.assertEqual(client.send.call_count,1)

    def test_timeout_blocks_resend_and_link_replacement(self):
        draft=self.invitation();client=Mock(send=Mock(side_effect=MailError('timeout',uncertain=True)))
        with self.assertRaises(MailError): self.send(draft,client)
        self.assertEqual(self.store.load()[0]['buyer_confirmation']['email_delivery']['state'],'unknown')
        with self.assertRaises(MailError): self.send(draft,client)
        with self.assertRaises(ConfirmationError): self.invitation(replace=True)
        self.assertEqual(client.send.call_count,1)

    def test_definitive_rejection_allows_explicit_retry_same_link(self):
        draft=self.invitation();client=Mock(send=Mock(side_effect=MailError('not authorised')))
        with self.assertRaises(MailError): self.send(draft,client)
        self.assertEqual(self.store.load()[0]['buyer_confirmation']['email_delivery']['state'],'rejected')
        client.send.side_effect=None;client.send.return_value='id'
        self.send(draft,client)
        self.assertEqual(self.store.load()[0]['buyer_confirmation']['email_delivery']['state'],'accepted')

    def test_pending_reservation_blocks_parallel_send_and_replacement(self):
        draft=self.invitation()
        def during_send(*args):
            with self.assertRaises(MailError): self.send(draft,Mock())
            with self.assertRaises(ConfirmationError): self.invitation(replace=True)
            return 'id'
        self.send(draft,Mock(send=Mock(side_effect=during_send)))

    def test_buyer_response_during_send_is_preserved(self):
        draft=self.invitation()
        def during_send(*args):
            respond(self.store,draft['token'],approved=True,name='Jane Buyer',attestation=True,now=self.now)
            return 'id'
        self.send(draft,Mock(send=Mock(side_effect=during_send)))
        invoice=self.store.load()[0]
        self.assertEqual(invoice['buyer_status'],'Confirmed')
        self.assertEqual(invoice['buyer_confirmation']['respondent_name'],'Jane Buyer')
        self.assertEqual(invoice['buyer_confirmation']['email_delivery']['state'],'accepted')

    def test_expired_or_replaced_link_cannot_be_sent(self):
        draft=self.invitation();client=Mock()
        replacement=self.invitation(replace=True)
        with self.assertRaises(ConfirmationError): self.send(draft,client)
        with self.assertRaises(ConfirmationError):
            send_confirmation_email(self.store,self.invoice['id'],replacement,client,
                now=self.now+timedelta(days=7))
        client.send.assert_not_called()


class MailTransportTests(unittest.TestCase):
    def test_authenticated_https_single_recipient_payload(self):
        response=Mock()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{"messageId":"id"}'
        opener=Mock(return_value=response)
        client=BrevoClient('private-key','sender@example.com',opener=opener)
        self.assertEqual(client.send('buyer@example.com',dict(subject='Confirmation',body='Hello'), 'attempt'),'id')
        request=opener.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(request.get_header('Api-key'),'private-key')
        self.assertEqual(payload['to'],[{'email':'buyer@example.com'}])
        self.assertEqual(payload['sender']['email'],'sender@example.com')
        self.assertEqual(payload['textContent'],'Hello')
        self.assertNotIn('bcc',payload)
        self.assertEqual(opener.call_args.kwargs['timeout'],20)

    def test_http_and_network_failures_are_distinct_and_redacted(self):
        for error,uncertain in [(HTTPError('https://example.com',401,'private-key',{},None),False),
                                (HTTPError('https://example.com',500,'private-key',{},None),True),
                                (URLError('private-key buyer@example.com'),True)]:
            client=BrevoClient('private-key','sender@example.com',opener=Mock(side_effect=error))
            with self.assertRaises(MailError) as caught:
                client.send('buyer@example.com',dict(subject='Test',body='Body'),'attempt')
            self.assertEqual(caught.exception.uncertain,uncertain)
            self.assertNotIn('private-key',str(caught.exception))
            self.assertNotIn('buyer@example.com',str(caught.exception))
