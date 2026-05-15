# 🚗 TÀI LIỆU HƯỚNG DẪN SỬ DỤNG: AUTO SALE XE AI (PHIÊN BẢN V2.0)

Hệ thống **Auto Sale Xe AI** là một dự án phần mềm ứng dụng **Trí tuệ nhân tạo (Gemini)** kết hợp với **Thao tác trình duyệt Website tự động (Playwright)**. Mục đích chính là biến quy trình bán một chiếc ô tô (bao gồm lên kịch bản dài dòng, phân tích tìm điểm nhấn SEO Facebook, và đi rải bài từng Group) thành một quy trình thu gọn chỉ với 1 Click chuột.

---

## 🛠️ PHẦN 1: HƯỚNG DẪN CÀI ĐẶT LẦN ĐẦU TRÊN MÁY TÍNH

Trước khi tận hưởng công cụ, bạn cần đảm bảo máy tính đã cài đặt lõi xử lý thư viện Python.

### 1. Cài Đặt Thư Viện Backend
Mở Terminal/CMD từ thư mục mã nguồn `sale xe/` và cài các Package nền tảng:
```bash
pip install -r requirements.txt
```

### 2. Tải Trình Duyệt Tự Động (Playwright)
Cài đặt nhân Chromium để tool điều khiển trình duyệt như người dùng thật. Nên dùng lệnh qua Python (đúng môi trường `pip` bạn đang chạy `app.py`):
```bash
python -m playwright install chromium
```
*(Nếu máy đã cài **Google Chrome** hoặc **Microsoft Edge**, chương trình có thể tự chuyển sang dùng trình duyệt đó khi Chromium bundle lỗi; khi không mở được cửa sổ, có thể chạy tạm ở chế độ **headless** — xem mục xử lý sự cố.)*

### 3. Thiết Lập API Key (Môi trường)
Hệ thống AI không tự nhiên sinh ra, nó dùng Engine của **Google Gemini**. Để AI hoạt động (thay vì in ra văn bản giả lập), bạn cần khởi tạo 1 file hoặc set biến môi trường:
*   `GEMINI_API_KEY`: API Key lấy từ Google AI Studio (Dùng để sinh bài chuẩn SEO).
*   *(Tùy chọn)* `FB_APP_ID`, `FB_ADS_TOKEN`: Nếu bạn muốn sau này chọc tới hệ thống **Facebook Ads Marketing** tự lấy hạn mức chạy thẻ. (Tham khảo file `ads_manager.py`).

---

## 💻 PHẦN 2: CÁCH SỬ DỤNG TRÊN GIAO DIỆN WEB

### Bước 1: Khởi Động Server Website
Tại CMD, khởi chạy máy chủ FastAPI Backend theo câu lệnh:
```bash
python app.py
```
*(Nếu cài đặt đúng, trình duyệt của bạn sẽ tự động bật link `http://127.0.0.1:8000`)*

### Bước 2: Thiết Lập Module Đăng Bài
Trên giao diện kính (Glassmorphism), bạn cấu hình **Thông tin Tài Khoản Đăng Bài**:
1.  **Tài khoản & Pass**: Chứa Nick bạn muốn dùng để đăng (An toàn nhất là nick trên các máy IP quen).
2.  **🔗 Danh sách Link Group/Tường (Target URL)**: Dán địa chỉ bài viết vào khung. VD:
    ```text
    https://www.facebook.com/groups/otocusaigon
    https://www.facebook.com/groups/chootomienbac
    ```
    *Dán mỗi Group 1 dòng (Nhấn Enter).*
3.  **Quãng Nghỉ (Delay)**: Chọn thời gian nghỉ ngậm (tương đối) giữa các lần chuyển trang Group. Khuyến nghị **20 - 30s** để né thuật toán Spam của FB.

### Bước 3: Cung Cấp Dữ Liệu Xe Nháp (Input Model)
Mục đích của AI Auto Sale Xe là bạn chỉ cần ném hình và chữ lộn xộn vào cho nó dọn dẹp.
*   **Hình Ảnh**: Ấn tải file nhiều góc độ xe.
*   **Keyword & Giá bán**: Đây là 2 cột chốt (Hệ thống AI ép buộc Facebook search Indexing ưu tiên dòng này).
*   **Kịch Bản Nháp**: Copy đoạn text tù mù, sai chính tả, miêu tả dài dòng v.v... vứt tất cả vào khung này. 
*   **Định Tỷ Lệ Quảng Cáo**: Chọn xem xe này bán cho "Gia Đình", hay "Giới Siêu Giàu (Luxury)" để AI nhắm đúng tệp ngôn ngữ.

### Bước 4: Kích Hoạt Quyền Trượng Vận Hành
Nhấn **Tiến Hành Tự Động Hóa**. 
Điều xảy ra lúc này:
1.  Bố cục Loading chạy. (API đang gọi xin lời văn mới từ Google Gemini).
2.  Tool điều khiển trình duyệt để đăng nhập & rải bài. Có **2 chế độ** (chọn 1):

#### Chế độ A (mặc định): Tool tự mở trình duyệt
2.1. Khoảng vài giây sau, cửa sổ trình duyệt (Chromium / Chrome / Edge tùy máy) mở ra.
2.2. **Bạn đăng nhập thủ công** (tự nhập tài khoản/mật khẩu, xử lý 2FA/checkpoint nếu có).
2.3. Khi bạn vào được trang chủ Facebook, bot tự mở lần lượt từng link Group/Tường và đăng bài.

#### Chế độ B (khuyên dùng khi 2FA): Dùng Chrome bạn mở sẵn (không bật cửa sổ mới)
Mục tiêu: bạn tự mở Chrome, tự login, sau đó tool **bám vào đúng cửa sổ Chrome đó** để thao tác.

**B1. Tắt hết Chrome đang chạy**, rồi mở Chrome với remote debugging (PowerShell):

```bash
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\chrome-cdp-sale-xe"
```

**B2. Trong Chrome vừa mở**, vào `https://www.facebook.com/` và đăng nhập sẵn (nếu muốn).
> Khuyến nghị: hãy **đăng nhập sẵn** để tránh bị gián đoạn lúc bot bắt đầu mở group.

**B3. Mở server kèm biến môi trường** (cùng cửa sổ PowerShell chạy backend):

```bash
$env:AUTO_SALE_XE_USE_EXISTING_CHROME="1"
python app.py
```

Ghi chú:
- Nếu bạn dùng port khác, set thêm:

```bash
$env:AUTO_SALE_XE_CHROME_CDP_URL="http://127.0.0.1:9222"
```

- Khi dùng chế độ B, tool **không tắt Chrome** sau khi chạy xong.

3.  Khi vào trang chủ thành công, bot tự rải link đi Post lần lượt danh sách Nhóm bạn gửi. Đưa ảnh, chép nội dung, và nhấn **ĐĂNG**. Xong 1 Group -> Nghỉ X giây -> Đi Group tiếp.

---

## 🚫 PHẦN 3: XỬ LÝ SỰ CỐ (TROUBLESHOOTING)

Facebook hay đổi cấu trúc trang (DOM), nên tool có thể lỗi theo thời gian nếu không còn bám đúng ô "Bạn đang nghĩ gì..." hoặc nút Đăng.

*   **Giao diện đăng bị văng**: Vào được group nhưng không đăng được (báo lỗi trong log). Cần cập nhật selector trong `services/fb_poster.py` (nút Post / composer).
*   **Lỗi khởi chạy Playwright / không mở được trình duyệt**:
    1. Cài lại Chromium đúng môi trường Python: `python -m playwright install chromium`.
    2. Trên **Windows**, backend chạy Playwright trong **thread riêng** (trong `fb_poster.py`) để tránh xung đột với Uvicorn — nếu vẫn lỗi, đọc nguyên văn thông báo trong giao diện web.
    3. Cài **Chrome** hoặc **Edge** bản chính thức; tool sẽ thử dùng kênh đó nếu Chromium bundle lỗi.
    4. Nếu log báo chạy **headless**: không có cửa sổ để xử lý 2FA; hãy sửa lỗi launch (cài Chromium/Chrome) để có cửa sổ thật.
*   **Đã vào trang chủ Facebook nhưng tool “không làm gì”** (đặc biệt khi dùng Chế độ B):
    - Đảm bảo bạn đã **restart backend** sau khi chỉnh code.
    - Chrome phải được mở bằng lệnh có `--remote-debugging-port=9222`. Nếu mở Chrome kiểu bình thường, tool **không bám** được.
    - Nếu tool bám nhầm tab (tab khác không phải Facebook), hãy đóng bớt tab hoặc để tab Facebook là tab đầu tiên.
    - Thử giảm danh sách URL xuống **1 link** để test trước.
    - Nếu link là Group riêng tư / cần “Tham gia nhóm”, bot sẽ không đăng được. Hãy dùng group bạn đã tham gia sẵn.
*   **Nhập Target URL đúng định dạng**:
    - Mỗi link 1 dòng.
    - Ví dụ đúng: `https://www.facebook.com/groups/xxxxx`
    - Tránh dán link có khoảng trắng đầu dòng/cuối dòng (tool có trim nhưng vẫn nên sạch).
*   **Số dư / Ads “ảo” hoặc cảnh báo Token**: Nếu chưa cấu hình `FB_ADS_TOKEN` (hoặc tương đương trong `ads_manager.py`), module Ads có thể dùng ngân sách giả lập — đây là hành vi dự phòng, không phải lỗi Playwright.
*   **Lỗi Textbox không xuống dòng**: AI đôi khi chèn văn bản theo một kiểu; phần lớn đã xử lý ở backend.

## Về phiên bản
- Phiên bản: `v2.0` (Mass Automation Release).
- Modules: `app.py`, `services/fb_poster.py`, `services/ai_generator.py`, `services/ads_manager.py`.
- Frontend: Vanilla HTML/JS, CSS Glassmorphism.
- Backend: FastAPI, Python-Multipart; Playwright (sync API + thread pool trên Windows).
