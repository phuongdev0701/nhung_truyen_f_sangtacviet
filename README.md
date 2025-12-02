Fanqie to Sangtacviet Auto Bot

Tool tự động hóa quy trình nhúng truyện từ trang FanqieNovel sang Sangtacviet sử dụng Python và Selenium.

Tính năng

Tự động đăng nhập Sangtacviet.

Quét danh sách truyện từ Fanqie (hỗ trợ tự động lật trang).

Tự động nhúng link vào Sangtacviet.

Menu điều khiển Console tiện lợi.

Lưu lịch sử các truyện đã làm để tránh trùng lặp.

Hỗ trợ nhập link Fanqie tùy chỉnh.

Cài đặt

Cài đặt Python.

Cài đặt thư viện:

pip install -r requirements.txt

Sử dụng

Mở file fanqie_to_stv_bot.py và điền tài khoản STV của bạn vào phần cấu hình:

STV_USERNAME = "YOUR_USERNAME"
STV_PASSWORD = "YOUR_PASSWORD"

Chạy tool:

python fanqie_to_stv_bot.py

Chọn các chức năng trên Menu (1, 2, 3) để sử dụng.

Nhấn q để dừng tool an toàn và quay về Menu.

Lưu ý

Tool sử dụng msvcrt nên chỉ hoạt động tốt trên Windows.
