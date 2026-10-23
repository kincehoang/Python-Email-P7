"""P7 – UEH KTX SmartNet. Python 3.9+, chỉ dùng thư viện chuẩn."""
import csv
import html
import mimetypes
import os
import queue
import re
import smtplib
import ssl
import threading
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html.parser import HTMLParser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

BASE = Path(__file__).resolve().parent
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
PROJECT_NAME = "UEH KTX SmartNet"
LANDING_URL = "http://nhom1-smartnet.infinityfreeapp.com"
LOG_FIELDS = ["time", "row", "name", "email", "mode", "status", "detail"]


@dataclass
class Recipient:
    row: int
    name: str
    email: str
    attachments: list
    error: str = ""


def read_recipients(csv_path):
    """UTF-8 BOM; dấu phẩy/chấm phẩy; đường dẫn tính từ thư mục CSV."""
    path = Path(csv_path).resolve()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        aliases = {"tên": "name", "ten": "name", "name": "name",
                   "email": "email", "tệp đính kèm": "attachment",
                   "tep dinh kem": "attachment", "attachment": "attachment",
                   "attachments": "attachment"}
        keys = [aliases.get((key or "").strip().lower(), (key or "").strip().lower())
                for key in (reader.fieldnames or [])]
        if not {"name", "email"}.issubset(keys):
            raise ValueError("CSV phải có cột Tên/Name và Email.")
        if len(keys) != len(set(keys)):
            raise ValueError("CSV có tên cột trùng nhau.")
        recipients = []
        for number, raw in enumerate(reader, 2):
            if not any(str(v or "").strip() for v in raw.values()):
                continue
            values = {key: (raw.get(original) or "").strip()
                      for original, key in zip(reader.fieldnames, keys)}
            name, email = values["name"], values["email"]
            problems = []
            if None in raw or any(value is None for value in raw.values()):
                problems.append("Số ô không khớp số cột CSV")
            if not name:
                problems.append("Thiếu tên")
            if not re.fullmatch(r"[^\s<>@,;\r\n]+@[^\s<>@,;\r\n]+\.[^\s<>@,;\r\n]+", email) or not email.isascii():
                problems.append("Email không hợp lệ (dùng địa chỉ ASCII)")
            if any(c in name for c in "\r\n"):
                problems.append("Tên chứa ký tự xuống dòng")
            attachments = []
            for item in values.get("attachment", "").split("|"):
                if item.strip():
                    target = Path(item.strip()).expanduser()
                    attachments.append(target if target.is_absolute() else path.parent / target)
            recipients.append(Recipient(number, name, email, attachments, "; ".join(problems)))
    if not recipients:
        raise ValueError("CSV không có người nhận.")
    return recipients


def render_template(template, recipient, escape_html=False):
    """Chỉ thay token được hỗ trợ, không tác động dấu ngoặc của CSS."""
    fields = {"name": recipient.name, "email": recipient.email,
              "project_name": PROJECT_NAME, "landing_url": LANDING_URL}
    return re.sub(r"\{(name|email|project_name|landing_url)\}",
                  lambda match: html.escape(fields[match[1]], quote=True)
                  if escape_html else fields[match[1]], template)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.hidden += 1
        if tag in ("p", "div", "br", "tr", "li", "h1", "h2"):
            self.parts.append("\n")
        if tag == "a":
            self.parts.extend(" " + value + " " for key, value in attrs if key == "href")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def build_message(recipient, sender, subject, template, common_files=()):
    if recipient.error:
        raise ValueError(recipient.error)
    message = EmailMessage()
    message["From"] = formataddr((PROJECT_NAME, sender))
    message["To"] = recipient.email
    message["Subject"] = render_template(subject, recipient)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    body = render_template(template, recipient, escape_html=True)
    parser = PlainText()
    parser.feed(body)
    message.set_content("".join(parser.parts).strip() or PROJECT_NAME)
    message.add_alternative(body, subtype="html")
    seen = set()
    for filename in [*common_files, *recipient.attachments]:
        path = Path(filename).resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy tệp đính kèm: {path.name}")
        mime, encoding = mimetypes.guess_type(path.name)
        main, sub = (mime if mime and not encoding else "application/octet-stream").split("/", 1)
        message.add_attachment(path.read_bytes(), maintype=main, subtype=sub, filename=path.name)
    return message


def append_log(path, record=None):
    """Ghi ngay từng dòng; ngăn ô dữ liệu bị hiểu thành công thức khi mở Excel."""
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    path = Path(path)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=LOG_FIELDS)
        if new:
            writer.writeheader()
        if record is not None:
            writer.writerow({key: safe(record.get(key, "")) for key in LOG_FIELDS})
        stream.flush()


def error_text(error, password=""):
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "Gmail từ chối xác thực. Kiểm tra tài khoản và App Password (535/534)."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "Máy chủ SMTP từ chối địa chỉ người nhận."
    detail = f"{type(error).__name__}: {error}"
    return detail.replace(password, "[đã ẩn]") if password else detail


def send_batch(recipients, sender, password, subject, template, common_files,
               dry_run, output_dir, notify, stop):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / ("preview_log.csv" if dry_run else "send_log.csv")
    append_log(log_path)  # Kiểm tra khả năng ghi trước mọi thao tác SMTP.
    successes = failures = 0
    for recipient in recipients:
        if stop.is_set():
            notify("info", "Đã dừng trước người nhận tiếp theo.")
            break
        mode = "CHẠY THỬ" if dry_run else "SMTP THẬT"
        try:
            message = build_message(recipient, sender, subject, template, common_files)
            if dry_run:
                preview = output_dir / "preview"
                preview.mkdir(exist_ok=True)
                (preview / f"email_{recipient.row:03d}.eml").write_bytes(message.as_bytes())
                (preview / f"email_{recipient.row:03d}.html").write_text(
                    message.get_body(preferencelist=("html",)).get_content(), encoding="utf-8")
                status, detail = "ĐÃ TẠO MẪU", "Đã xuất EML/HTML; chưa gửi email."
            else:
                notify("info", f"Đang kết nối {SMTP_SERVER}:{SMTP_PORT} → {recipient.email}")
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                    server.login(sender, password)
                    refused = server.send_message(message)
                    if refused:
                        raise smtplib.SMTPRecipientsRefused(refused)
                status, detail = "THÀNH CÔNG", "SMTP đã chấp nhận thư; cần kiểm tra hộp thư/Spam."
            successes += 1
        except Exception as error:
            status, detail = "THẤT BẠI", error_text(error, password)
            failures += 1
        record = dict(time=datetime.now().astimezone().isoformat(timespec="seconds"),
                      row=recipient.row, name=recipient.name, email=recipient.email,
                      mode=mode, status=status, detail=detail)
        notify("record", record)
        try:
            append_log(log_path, record)
        except OSError as error:
            notify("info", f"LỖI GHI LOG: {error}. Đã dừng để tránh mất nhật ký.")
            break
    notify("info", f"Hoàn tất: {successes} xử lý thành công, {failures} thất bại. Log: {log_path}")


class EmailApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UEH KTX SmartNet | Gửi Email nâng cao – Phần 7")
        self.geometry("1040x790")
        self.minsize(860, 650)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.common_files = []
        self.csv_path = tk.StringVar(value=str(BASE / "recipients.csv"))
        self.subject = tk.StringVar(value="{name}, khám phá UEH KTX SmartNet")
        self.dry_run = tk.BooleanVar(value=True)
        self.files_label = tk.StringVar(value="Chưa chọn tệp chung; vẫn đọc tệp riêng trong CSV.")
        self.output_path = tk.StringVar(value=str(BASE / "results"))
        panel = ttk.Frame(self, padding=18)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="UEH KTX SmartNet", font=("Arial", 23, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(panel, text="Gmail SMTP • 587 • STARTTLS • App Password qua biến môi trường").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))
        ttk.Label(panel, text="Danh sách CSV").grid(row=2, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.csv_path).grid(row=2, column=1, sticky="ew", padx=8)
        ttk.Button(panel, text="Chọn CSV", command=self.choose_csv).grid(row=2, column=2)
        ttk.Label(panel, text="Đính kèm chung").grid(row=3, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.files_label, wraplength=560).grid(row=3, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(panel, text="Chọn / thay tệp", command=self.choose_files).grid(row=3, column=2)
        ttk.Button(panel, text="Bỏ tệp chung", command=self.clear_files).grid(row=4, column=2)
        ttk.Label(panel, text="Tiêu đề").grid(row=5, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.subject).grid(row=5, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        ttk.Label(panel, text="Nội dung HTML · Token: {name}, {email}, {project_name}, {landing_url}").grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(panel, text="Mở template HTML", command=self.load_html).grid(row=6, column=2)
        self.body = scrolledtext.ScrolledText(panel, height=12, wrap="word", font=("Courier", 11))
        self.body.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self.body.insert("1.0", (BASE / "template.html").read_text(encoding="utf-8"))
        panel.rowconfigure(7, weight=2)
        ttk.Label(panel, text="Thư mục kết quả").grid(row=8, column=0, sticky="w", pady=8)
        ttk.Entry(panel, textvariable=self.output_path).grid(row=8, column=1, sticky="ew", padx=8)
        ttk.Button(panel, text="Chọn thư mục", command=self.choose_output).grid(row=8, column=2)
        actions = ttk.Frame(panel)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(actions, text="Chạy thử: tạo EML/HTML, không gửi thư", variable=self.dry_run).pack(side="left")
        self.send_button = ttk.Button(actions, text="Gửi Email", command=self.start_send)
        self.send_button.pack(side="right")
        self.stop_button = ttk.Button(actions, text="Dừng sau thư hiện tại", command=self.stop.set, state="disabled")
        self.stop_button.pack(side="right", padx=8)
        ttk.Label(panel, text="Trạng thái trực tiếp / nhật ký từng người nhận").grid(row=10, column=0, columnspan=3, sticky="w")
        self.status = scrolledtext.ScrolledText(panel, height=11, state="disabled", wrap="word", font=("Arial", 11))
        self.status.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        panel.rowconfigure(11, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Control-Return>", lambda event: self.start_send())
        self.bind("<Control-o>", lambda event: self.choose_csv())
        self.bind("<Control-l>", lambda event: self.load_html())
        self.after(100, self.poll_events)

    def choose_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.csv_path.set(path)

    def choose_files(self):
        files = filedialog.askopenfilenames(title="Chọn tệp chung cho mọi người nhận")
        if files:
            self.common_files = list(files)
            self.files_label.set("; ".join(Path(path).name for path in files))

    def clear_files(self):
        self.common_files = []
        self.files_label.set("Không có tệp chung.")

    def choose_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_path.set(path)

    def load_html(self):
        path = filedialog.askopenfilename(filetypes=[("HTML", "*.html *.htm")])
        if path:
            try:
                content = Path(path).read_text(encoding="utf-8-sig")
                self.body.delete("1.0", "end")
                self.body.insert("1.0", content)
            except (OSError, UnicodeError) as error:
                messagebox.showerror("Không đọc được HTML", str(error))

    def write_status(self, text):
        self.status.configure(state="normal")
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def start_send(self):
        if self.running:
            return
        try:
            recipients = read_recipients(self.csv_path.get())
            subject = self.subject.get().strip()
            template = self.body.get("1.0", "end-1c")
            if not subject or not template.strip():
                raise ValueError("Cần nhập tiêu đề và nội dung HTML.")
            if "\n" in subject or "\r" in subject:
                raise ValueError("Tiêu đề không được xuống dòng.")
            dry_run = self.dry_run.get()
            sender = os.environ.get("SENDER_EMAIL", "").strip()
            password = os.environ.get("SENDER_APP_PASSWORD", "")
            if not dry_run and (not sender or not password):
                raise ValueError("Thiết lập SENDER_EMAIL và SENDER_APP_PASSWORD trước khi chạy GUI.")
            sender = sender or "demo@example.com"
            if not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", sender) or not sender.isascii():
                raise ValueError("Địa chỉ người gửi không hợp lệ.")
            output = Path(self.output_path.get()).expanduser().resolve()
            if not dry_run and not messagebox.askyesno("Xác nhận gửi email thật",
                    f"Gửi đến {len(recipients)} dòng từ {sender}?\nKiểm tra địa chỉ trong CSV trước khi gửi."):
                return
        except (OSError, ValueError, UnicodeError, csv.Error) as error:
            messagebox.showerror("Kiểm tra dữ liệu", str(error))
            return
        self.running = True
        self.stop.clear()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.write_status(f"Bắt đầu {'CHẠY THỬ' if dry_run else 'SMTP THẬT'}: {len(recipients)} dòng.")
        args = (recipients, sender, password, subject, template, tuple(self.common_files),
                dry_run, output, lambda kind, value: self.events.put((kind, value)), self.stop)
        def worker():
            try:
                send_batch(*args)
            except Exception as error:
                self.events.put(("info", error_text(error, password)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "record":
                    self.write_status(f"[{value['time']}] {value['name']} <{value['email']}> | {value['status']} | {value['detail']}")
                elif kind == "done":
                    self.running = False
                    self.send_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                else:
                    self.write_status(value)
        except queue.Empty:
            pass
        self.after(100, self.poll_events)

    def on_close(self):
        if self.running:
            self.stop.set()
            messagebox.showinfo("Đang dừng", "Đợi thư hiện tại hoàn tất hoặc hết timeout rồi đóng cửa sổ.")
        else:
            self.destroy()


if __name__ == "__main__":
    EmailApp().mainloop()
