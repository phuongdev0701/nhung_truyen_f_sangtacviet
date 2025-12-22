uto Novel Embedder Ultimate (Fanqie, Jjwxc, Qimao, Ciweimao, SFACG, 69shu, Quanben5 -> Sangtacviet)

Tool tự động hóa quy trình nhúng truyện từ 7 nguồn truyện Trung Quốc phổ biến sang hệ thống Sangtacviet.app sử dụng Python và Selenium.

Phiên bản này sử dụng kiến trúc Đa Luồng (Multi-threading) với 2 trình duyệt chạy song song để đạt tốc độ tối đa.

🌟 Tính Năng Nổi Bật

1. Hỗ Trợ 7 Nguồn Truyện Lớn

🍅 Fanqie (Cà Chua): Hỗ trợ lọc truyện mới (<= 2 ngày), chế độ chạy vòng lặp vô tận.

🌿 Jjwxc (Tấn Giang): Quét theo danh sách tác giả hoặc bảng xếp hạng.

🐱 Qimao (Thất Miêu): Tự động nhận diện và quét danh sách.

🦔 Ciweimao (Thất Vĩ Miêu): Hỗ trợ quét danh sách phân loại.

🍍 SFACG (B菠萝包): Hỗ trợ quét theo trang (PageIndex).

📖 69shu (Lục Cửu): Hỗ trợ quét truyện lẻ hoặc danh sách.

📚 Quanben5 (Toàn Bản 5): Hỗ trợ quét danh sách phân loại.

2. Kiến Trúc Song Song (Parallel Processing)

Tool chạy 2 cửa sổ Chrome cùng lúc:

Scanner (Trình duyệt Trái): Chuyên đi quét link truyện mới từ nguồn.

Embedder (Trình duyệt Phải): Chuyên túc trực tại Sangtacviet để nhúng link ngay khi nhận được từ Scanner.

Ưu điểm: Không phải chờ đợi chuyển đổi tab, tận dụng tối đa thời gian.

3. Cơ Chế Thông Minh & An Toàn

Fast Mode & Anti-1015 (Menu 1 & 8): Chế độ đặc biệt cho Fanqie.

Tự động phát hiện lỗi chặn 1015 (Rate Limit) của Cloudflare.

Tự động ngủ đông 60 giây và thử lại nếu bị chặn.

Tự động bỏ qua (Skip) truyện lỗi để không làm treo tool.

Persistent Drivers (Giữ Profile): Khi bạn bấm dừng (q), trình duyệt KHÔNG TẮT. Bạn có thể giữ nguyên phiên đăng nhập để chạy tiếp link khác mà không cần login lại.

Smart Filter:

Tự động bỏ qua truyện đã nhúng (Check trùng ID trong file lịch sử).

Chỉ lấy truyện có cập nhật mới (<= 2 ngày) đối với các nguồn hỗ trợ check ngày.

Auto-Pagination: Tự động lật trang (Page 1 -> Page 2...) liên tục.

🛠️ Yêu Cầu Hệ Thống

Hệ điều hành: Windows (Tool sử dụng thư viện msvcrt để bắt phím tắt).

Python: Phiên bản 3.7 trở lên.

Google Chrome: Phiên bản mới nhất.

📦 Cài Đặt

Cài đặt thư viện Python:
Mở CMD hoặc Terminal tại thư mục chứa tool và chạy lệnh:

pip install selenium webdriver-manager


Cấu hình Tài khoản:
Mở file fanqie_to_stv_bot.py bằng trình soạn thảo (Notepad, VS Code...) tìm đến dòng:

# --- CẤU HÌNH TÀI KHOẢN ---
STV_USERNAME = "Tên_Đăng_Nhập_Của_Bạn"
STV_PASSWORD = "Mật_Khẩu_Của_Bạn"


Cấu hình Lưu trữ (Tùy chọn):
Mặc định file lịch sử lưu tại D:\nhúng truyện fanqie, qidian,qimao\da_lam_xong.txt. Bạn có thể sửa biến HISTORY_DIR trong code nếu muốn đổi chỗ.

🚀 Hướng Dẫn Sử Dụng

Chạy tool bằng lệnh:

python fanqie_to_stv_bot.py


Giải Thích Menu

1. Chạy Fanqie (Cà Chua): (Khuyên dùng) Nhập link bất kỳ. Kích hoạt chế độ Fast Mode + Anti-1015.

2 - 7. Chạy các nguồn khác: Nhập link danh sách tương ứng (xem ví dụ trong tool).

8. Chạy Fanqie (Loop 700 -> 3000): Chế độ "cày cuốc". Tool tự động chạy từ trang 700 đến 3000, sau đó quay lại 700 và lặp lại mãi mãi.

9. Mở 2 Trình duyệt để treo: Chỉ mở 2 cửa sổ Chrome lên và tự động đăng nhập Sangtacviet, sau đó để yên cho bạn kiểm tra hoặc giữ session.

10. Xem tổng số ID: Kiểm tra xem đã nhúng được bao nhiêu truyện.

0. Thoát: Đóng toàn bộ trình duyệt và tắt tool.

Cách Dừng Tool (Quan Trọng)

Bấm vào cửa sổ dòng lệnh (CMD/Terminal).

Nhấn phím q trên bàn phím.

Cơ chế dừng:

Scanner: Dừng quét ngay lập tức.

Embedder: Sẽ chạy nốt những truyện đang còn trong hàng đợi (Queue) để đảm bảo không bị sót, sau đó mới dừng hẳn.

Lưu ý: Sau khi dừng, 2 cửa sổ Chrome vẫn mở. Bạn có thể chọn chức năng khác trên Menu để chạy tiếp ngay lập tức.

⚠️ Lưu Ý Khi Sử Dụng

Lỗi 1015 (Rate Limit): Nếu thấy dòng thông báo màu đỏ [!!!] BỊ CHẶN 1015, hãy để yên. Tool sẽ tự động nghỉ 60s rồi chạy lại. Đừng tắt tool vội.

File Lịch sử (da_lam_xong.txt): Đây là "bộ nhớ" của tool. Nếu bạn xóa file này, tool sẽ nhúng lại từ đầu các truyện cũ.

Tọa độ cửa sổ: Tool được cài đặt để mở 1 cửa sổ ở góc trái (0,0) và 1 cửa sổ ở góc phải (960,0). Đừng thay đổi kích thước màn hình quá nhiều để dễ quan sát.