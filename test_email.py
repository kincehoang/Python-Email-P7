"""Kiểm thử offline: không kết nối mạng, không gửi email."""
import csv
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import send_email_gui as app


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.template = (app.BASE / "template.html").read_text(encoding="utf-8")
        self.people = app.read_recipients(app.BASE / "recipients.csv")

    def test_csv_and_mime(self):
        self.assertEqual(len(self.people), 3)
        person = app.Recipient(2, '<Minh & Hiền>', 'demo@example.com', self.people[0].attachments)
        message = app.build_message(person, 'sender@example.com', 'Chào {name}', self.template)
        body = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('&lt;Minh &amp; Hiền&gt;', body)
        self.assertEqual(message.get_content_type(), 'multipart/mixed')
        self.assertIsNotNone(message.get_body(preferencelist=('plain',)))
        self.assertEqual(len(list(message.iter_attachments())), 1)
        self.assertIn('UEH KTX', list(message.iter_attachments())[0].get_content())
        self.assertEqual(message['To'], 'demo@example.com')

    def test_semicolon_bom_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.csv'
            path.write_text('Tên;Email;Tệp đính kèm\nMinh;minh@example.com;one.txt|two.txt\n', encoding='utf-8-sig')
            person = app.read_recipients(path)[0]
            self.assertEqual(person.attachments, [Path(tmp).resolve() / 'one.txt', Path(tmp).resolve() / 'two.txt'])

    def test_batch_continues_after_bad_row_and_missing_file(self):
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(app.smtplib, 'SMTP', side_effect=AssertionError('Offline mode used network')):
                app.send_batch(app.read_recipients(app.BASE / 'recipients_errors.csv'),
                               'demo@example.com', '', 'Hello {name}', self.template, (), True, tmp,
                               lambda kind, value: events.append((kind, value)), threading.Event())
            with (Path(tmp) / 'preview_log.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row['status'] for row in rows], ['ĐÃ TẠO MẪU', 'THẤT BẠI', 'THẤT BẠI'])
            self.assertTrue((Path(tmp) / 'preview/email_002.eml').exists())
            self.assertIn('không hợp lệ', rows[1]['detail'])
            self.assertIn('Không tìm thấy', rows[2]['detail'])

    def test_smtp_inheritance_and_no_cross_recipient_disclosure(self):
        calls = []
        class SMTPStub:
            def __init__(self, host, port, timeout):
                calls.append((host, port, timeout))
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def ehlo(self):
                calls.append('ehlo')
            def starttls(self, context):
                calls.append('starttls')
                self.tls = context
            def login(self, sender, password):
                calls.append(('login', sender, password))
            def send_message(self, message):
                calls.append(('send', str(message['To'])))
                return {}
        with tempfile.TemporaryDirectory() as tmp, patch.object(app.smtplib, 'SMTP', SMTPStub):
            app.send_batch(self.people[:1], 'sender@example.com', 'fake-secret', 'Hi', self.template,
                           (), False, tmp, lambda *args: None, threading.Event())
        self.assertEqual(calls, [('smtp.gmail.com', 587, 30), 'ehlo', 'starttls', 'ehlo',
                                 ('login', 'sender@example.com', 'fake-secret'), ('send', 'ducminh@example.com')])

    def test_stop_and_log_formula(self):
        stop = threading.Event()
        stop.set()
        with tempfile.TemporaryDirectory() as tmp:
            app.send_batch(self.people, 'demo@example.com', '', 'Hi', self.template, (), True,
                           tmp, lambda *args: None, stop)
            self.assertFalse((Path(tmp) / 'preview').exists())
            path = Path(tmp) / 'formula.csv'
            app.append_log(path, {'name': '=1+1'})
            self.assertIn("'=1+1", path.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
