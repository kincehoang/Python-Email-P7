# Phần 7 — UEH KTX SmartNet

Bộ nâng cấp độc lập từ nội dung P6; không sửa tài liệu hay source P1–P6. Chỉ dùng thư viện chuẩn Python 3.9 trở lên và Tkinter.

## Chạy ngay

1. Giải nén, mở terminal trong thư mục `Phan7_SmartNet`.
2. Chạy `python3 send_email_gui.py` (Windows: `py send_email_gui.py`).
3. Giữ dấu chọn **Chạy thử**, bấm **Gửi Email**. CSV và template đã được nạp sẵn. Không cần mật khẩu cho chế độ này.
4. Xem trạng thái trực tiếp, `results/preview_log.csv`, và `results/preview/*.html`, `*.eml`. Mở HTML bằng trình duyệt, EML bằng ứng dụng đọc thư để xem MIME/attachment.
5. Chọn `recipients_errors.csv`, chạy thử để minh họa lỗi địa chỉ và thiếu tệp. Thư mục kết quả có thể đổi bằng GUI để tách các phiên.

Phím tắt: `Ctrl+Enter` bắt đầu xử lý, `Ctrl+O` chọn CSV, `Ctrl+L` mở template HTML.

Chạy demo không cần mở cửa sổ: `python3 run_demo.py`. Kiểm thử offline: `python3 -m unittest -v test_email.py`.

GUI cần Python có Tkinter hoạt động. Có thể kiểm tra bằng `python3 -m tkinter`. Nếu Python hệ thống macOS dùng Tk cũ gặp lỗi, dùng Python từ python.org kèm Tk; Ubuntu/Debian có thể cần gói `python3-tk`. Không cần pip cho chương trình này.

## Gửi Gmail thật

Thay các địa chỉ `example.com` trong CSV bằng email thử nghiệm của nhóm. Đây là địa chỉ mẫu, không phải địa chỉ thành viên thật. Kiểm tra tệp đính kèm trước khi gửi.

macOS/Linux (nhập trong terminal rồi chạy chương trình từ terminal đó):

```sh
export SENDER_EMAIL='email-gui-cua-ban@gmail.com'
read -s SENDER_APP_PASSWORD
export SENDER_APP_PASSWORD
python3 send_email_gui.py
```

Sau lệnh `read -s`, nhập App Password rồi nhấn Enter. PowerShell:

```powershell
$env:SENDER_EMAIL = 'email-gui-cua-ban@gmail.com'
$secret = Read-Host 'App Password' -AsSecureString
$env:SENDER_APP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
py send_email_gui.py
```

Bỏ chọn **Chạy thử**, bấm **Gửi Email**, xem lại số người nhận trong hộp xác nhận. Code dùng `smtp.gmail.com:587`, EHLO → STARTTLS với xác minh chứng chỉ → EHLO → login bằng App Password → send_message, timeout 30 giây, kế thừa phương thức P6. Mỗi người nhận có một email riêng.

P6 trên Docs bị thiếu phần đầu code: chưa thấy chuỗi tên biến trong lệnh `os.getenv`, cũng chưa thấy phép gán SMTP_SERVER. Bản P7 dùng hostname Gmail chuẩn `smtp.gmail.com` theo mô tả P6 và chọn tên biến môi trường `SENDER_EMAIL`, `SENDER_APP_PASSWORD` trùng các biến Python đang xuất hiện trong đoạn code. Khi nhận được file P6 gốc, đối chiếu tên biến môi trường; nếu khác, đặt hai biến P7 từ cùng giá trị xác thực của P6. Không đổi nhà cung cấp, cổng hoặc cơ chế STARTTLS/App Password.

## Quy ước CSV và HTML

- UTF-8 hoặc UTF-8 BOM. Cột `Tên,Email,Tệp đính kèm` hoặc `name,email,attachment`. Nhận dấu phân cách phẩy/chấm phẩy.
- Nhiều tệp riêng: ngăn bằng `|`. Đường dẫn tương đối tính từ thư mục chứa CSV; hỗ trợ đường dẫn tuyệt đối. Tệp chung chọn trong GUI được gửi cùng tệp riêng; loại bỏ tệp trùng đường dẫn.
- Địa chỉ không hợp lệ, tên trống hoặc thiếu tệp được ghi thất bại và tiếp tục dòng sau. Kiểm tra định dạng không chứng minh hộp thư tồn tại.
- Token hỗ trợ: `{name}`, `{email}`, `{project_name}`, `{landing_url}`. Tên/địa chỉ được escape khi chèn vào HTML; dấu ngoặc trong CSS không bị thay.
- Liên kết Landing Page giữ URL HTTP đang ghi ở P3; không tự khẳng định trang đã có HTTPS. Đổi hằng `LANDING_URL` nếu nhóm cung cấp URL mới.
- Tệp đính kèm được đọc vào bộ nhớ. Nên thử bằng tệp nhỏ; giới hạn Gmail còn phụ thuộc kích thước MIME sau mã hóa.

## Log, minh chứng và giới hạn

`send_log.csv` chỉ dành cho SMTP thật; `preview_log.csv` dành cho tạo mẫu offline. Log append có thời gian kèm múi giờ máy chạy, dòng CSV, tên, email, chế độ, trạng thái và lý do. Không ghi App Password. Dữ liệu bắt đầu bằng ký tự công thức được thêm dấu nháy đơn khi ghi CSV để mở bằng bảng tính an toàn.

**THÀNH CÔNG** nghĩa là máy chủ SMTP chấp nhận thư, chưa chứng minh thư đã tới Inbox. Cần chụp thêm hộp thư người nhận/Spam và tệp tải về. **ĐÃ TẠO MẪU** chỉ là tạo EML/HTML, không được trình bày thành gửi Gmail thành công. Khi kết nối gián đoạn vào thời điểm truyền thư, kết quả có thể không chắc chắn; kiểm tra Sent/Inbox trước khi tự gửi lại. Chương trình không tự retry.

Luồng nền xử lý SMTP; hàng đợi và `after()` cập nhật GUI. Nút dừng có hiệu lực trước người nhận tiếp theo; thư đang xử lý vẫn đợi phản hồi/timeout. Không đóng cưỡng bức khi đang gửi nếu muốn bảo toàn log. Không upload chương trình Python, log có địa chỉ thật hoặc thông tin xác thực lên hosting công khai.

Đọc `BAO_CAO_PHAN_7.md` để dán vào thẻ P7; đọc `DOI_CHIEU_VA_DONG_GOI.md` để tổng hợp source toàn nhóm. Thư mục `results/demo_*` được tạo bằng chạy thử, không phải minh chứng gửi thư thật.

Đã điền báo cáo, source chương trình, dữ liệu mẫu và bốn ảnh vào [thẻ P7 trong Google Docs](https://docs.google.com/document/d/1usDPuH-wgye_IfInxgCLpiJolxhcpAWICyQgwM5HrAU/edit?tab=t.5trjis2dkixz). Ảnh gốc nằm trong `minh_chung/`; log của hai phiên GUI trong `results/preview_log.csv`. P1–P6 đã được đối chiếu không thay đổi. Chưa gửi Gmail thật.
