# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Giới thiệu

Crawler thu thập thông tin sách tiếng Việt trên stbook.vn (trang bán sách
điện tử/sách giấy của NXB Chính trị Quốc gia Sự thật), lưu theo từng danh
mục có sẵn trên site. Có thể tải thêm ảnh bìa và toàn bộ nội dung PDF của
các sách "Miễn phí" đọc được online (nội dung có bản quyền — xem lưu ý
trong README.md trước khi bật `--download-pdf`).

## Lệnh thường dùng

```bash
uv sync                                    # cài dependency (dùng uv, không dùng pip/requirements.txt)

python -m stbook_crawler.main              # crawl toàn bộ 15 danh mục, chỉ metadata
python -m stbook_crawler.main --category kinh-dien --category kinh-te   # test nhanh 1-2 danh mục
python -m stbook_crawler.main --skip-detail                             # bỏ trang chi tiết (không dùng cùng --download-pdf)
python -m stbook_crawler.main --download-covers                          # kèm tải ảnh bìa
python -m stbook_crawler.main --download-pdf --max-pages 20              # test tải PDF, giới hạn trang
python -m stbook_crawler.main --download-pdf --workers 8                 # tải trọn nội dung PDF (mặc định tắt)
python -m stbook_crawler.main --help                                      # xem toàn bộ cờ

# Trên server GPU Run:ai: chạy nền kèm tiến trình giữ GPU (cần torch, đã có trong dependency)
source .venv/bin/activate && ./scripts/run_with_gpu_keepalive.sh --download-pdf
```

Không có bộ test, linter, hay build step nào được cấu hình trong repo này
(không có `tests/`, không có config pytest/ruff/mypy). Cách xác nhận thay
đổi hoạt động đúng là chạy trực tiếp `python -m stbook_crawler.main` với
`--category` giới hạn 1 danh mục nhỏ (và `--max-pages` nhỏ nếu đụng tới
`content.py`) rồi kiểm tra output trong `data/`.

## Kiến trúc

Pipeline tuần tự qua từng danh mục, trong mỗi danh mục xử lý tuần tự từng
sách (`main.py::crawl` → `_process_book`), nhưng việc tải nội dung PDF của
*một* cuốn sách thì chạy song song ở tầng ảnh (`content.py`). Hai tầng
song song này dùng 2 loại session HTTP khác nhau, không dùng lẫn:

- `client.RateLimitedSession` — dùng cho mọi request lấy metadata (danh
  sách sách, trang chi tiết, ảnh bìa). Tự chèn delay tối thiểu giữa các
  request liên tiếp (`--delay`, mặc định 0.8s) để crawl lịch sự, và tự
  retry lỗi tạm thời (5xx, timeout) qua `urllib3.Retry`.
- `client.build_bulk_session` — dùng riêng cho tải nội dung PDF
  (`content.download_book_pages`), KHÔNG rate-limit theo delay tuần tự vì
  tốc độ được khống chế bằng số worker của `ThreadPoolExecutor`
  (`--workers`, mặc định 8 — đã đo thực tế server không phản hồi nhanh
  hơn dù mở nhiều kết nối hơn). Pool size của session phải >= số worker
  để tránh nghẽn cổ chai ở connection pool.

Luồng dữ liệu qua các module:

1. `categories.py` — danh sách tĩnh 15 danh mục cố định (`slug`, `p_id`,
   `name`), lấy từ menu trang chủ; không cần crawl để có danh sách này.
2. `parse_category.py` — với mỗi danh mục, phân trang qua
   `/category/<slug>/<p_id>/<offset>` (offset bước 15) để lấy danh sách
   sách cơ bản (`BookListItem`).
3. `parse_detail.py` — với mỗi sách, gọi `/store_detail/x/<product_id>`
   để lấy mô tả, tác giả đầy đủ, `info` (số trang, năm XB...), và
   `can_read_online`. Có thể bỏ qua bằng `--skip-detail`.
4. `content.py` — chỉ chạy khi `--download-pdf` và sách là "Miễn phí" +
   đọc được online (`main._is_free_readable`). Mỗi trang sách = 4 ảnh
   PNG ghép từ trình đọc turn.js
   (`/cbs20/download_preview/img.json/<product_code>/img_short_<1-4><trang>/_READ`).
   Toàn bộ `4*num_pages` request ảnh góc được xếp vào một hàng đợi chung
   và xử lý song song, ghép lại, thu nhỏ + nén JPEG, rồi ghép thành 1 PDF
   bằng Pillow. Lỗi mạng/timeout khi tải 1 ảnh góc được retry vô hạn với
   backoff tăng dần (không bao giờ bỏ trang chỉ vì server chậm tạm
   thời); các lỗi khác (vd. content-type không phải ảnh, do sách "đang
   cập nhật") thì bỏ qua trang đó và ghi log cảnh báo, không dừng cả
   crawl.
5. `storage.py` — ghi/đọc `data/<slug>/books.json` (từng danh mục) và
   `data/all_books.json` (gộp toàn bộ). Đây cũng là cơ chế resume: mỗi
   sách xử lý xong được ghi ngay ra `books.json`, nên chạy lại đúng lệnh
   cũ sau khi bị ngắt (mất mạng, Ctrl+C, crash...) sẽ đọc lại file cũ và
   chỉ crawl tiếp phần còn thiếu thay vì làm lại từ đầu — xem
   `main.py::_process_book` và `storage.load_category_books`.
6. `main.py` — CLI (argparse) điều phối toàn bộ pipeline trên, xử lý
   resume, ghi thêm log ra `<out>/crawl.log`, và không để lỗi ở 1 danh
   mục/1 sách làm hỏng cả tiến trình (bắt exception ở từng tầng, log
   cảnh báo rồi tiếp tục).

Mọi lỗi cục bộ (1 sách, 1 danh mục, 1 ảnh góc) đều được bắt và ghi log
cảnh báo thay vì để crash toàn bộ job — đây là nguyên tắc thiết kế xuyên
suốt codebase, cần giữ khi sửa/thêm code mới.

`data/` không commit vào git (dữ liệu crawl ra, không phải mã nguồn).
