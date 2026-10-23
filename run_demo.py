"""Tạo kết quả minh họa offline bằng đúng các hàm của GUI."""
import threading
from send_email_gui import BASE, read_recipients, send_batch


if __name__ == '__main__':
    template = (BASE / 'template.html').read_text(encoding='utf-8')
    def notify(kind, value):
        if kind == 'record':
            print(f"{value['time']} | {value['name']} | {value['status']} | {value['detail']}")
        else:
            print(value)
    for csv_name, directory in [('recipients.csv', 'demo_success'), ('recipients_errors.csv', 'demo_errors')]:
        print(f'\nCHẠY THỬ OFFLINE: {csv_name}')
        send_batch(read_recipients(BASE / csv_name), 'demo@example.com', '',
                   '{name}, khám phá UEH KTX SmartNet', template, (), True,
                   BASE / 'results' / directory, notify, threading.Event())
