# stbook-crawler

Công cụ thu thập (crawl) thông tin sách tiếng Việt trên [stbook.vn](https://stbook.vn/)
— trang bán sách điện tử/sách giấy của Nhà xuất bản Chính trị Quốc gia Sự thật —
và lưu lại theo đúng từng danh mục (mục/topic) đã có sẵn trên website.

## Website hoạt động thế nào (kết quả inspect)

- Trang danh mục: `https://stbook.vn/category/<slug>/<p_id>/<offset>`
  (`offset` bắt đầu từ 0, mỗi trang có tối đa 15 sách). Danh sách 15 danh
  mục cố định (Kinh điển, Kinh tế, Pháp luật, ...) nằm trong
  [`categories.py`](src/stbook_crawler/categories.py), lấy từ menu
  "Danh mục sách" ở trang chủ.
- Trang chi tiết 1 sách: `https://stbook.vn/store_detail/<slug-bất-kỳ>/<p_id>`
  — phần slug chỉ để đẹp URL, server chỉ dựa vào `p_id`.
- Với các sách ghi "Bản điện tử: Miễn phí" và có nút "Xem ngay", nội dung
  được phục vụ qua một trình đọc dạng lật trang (turn.js): mỗi trang sách
  là 4 ảnh PNG độ phân giải cao ghép lại, tải qua
  `/cbs20/download_preview/img.json/<product_code>/img_short_<1-4><trang>/_READ`.
  **Đây là dữ liệu có bản quyền** — xem phần "Về việc tải nội dung sách"
  bên dưới trước khi bật tính năng này.
- Không tìm thấy `robots.txt` hợp lệ trên site tại thời điểm inspect.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Sử dụng

```bash
# Crawl toàn bộ 15 danh mục, chỉ lấy metadata (tên, tác giả, giá, mô tả...)
python -m stbook_crawler.main

# Chỉ crawl 1 (hoặc vài) danh mục cụ thể, để test nhanh
python -m stbook_crawler.main --category kinh-dien --category kinh-te

# Bỏ qua trang chi tiết cho nhanh (mất mô tả, tác giả đầy đủ, số trang...)
python -m stbook_crawler.main --skip-detail

# Tải kèm ảnh bìa
python -m stbook_crawler.main --download-covers

# Tải TOÀN BỘ nội dung các sách "Miễn phí" đọc được online, ghép thành PDF
python -m stbook_crawler.main --download-pdf

# Giới hạn số trang mỗi sách (ví dụ chỉ lấy 20 trang đầu làm bản xem trước)
python -m stbook_crawler.main --download-pdf --max-pages 20
```

Chạy `python -m stbook_crawler.main --help` để xem đầy đủ các cờ.

Crawler tôn trọng máy chủ: mặc định nghỉ 0.8 giây giữa hai request
(`--delay` để chỉnh), tự động thử lại khi gặp lỗi tạm thời.

## Kết quả đầu ra

```
data/
  kinh-dien/
    books.json          # toàn bộ sách của riêng danh mục "Kinh điển"
    covers/              # ảnh bìa, nếu bật --download-covers
    content/<id>/        # ảnh các trang xem thử, nếu bật --fetch-content
  kinh-te/
    books.json
  ...
  all_books.json         # gộp toàn bộ sách của mọi danh mục đã crawl
```

Mỗi cuốn sách trong `books.json` gồm: `product_id`, `title`, `author(s)`,
`product_code`, `cover_url`, `price_paper`, `price_ebook`, `category_name`,
`description`, `info` (năm xuất bản, số trang, khổ cỡ, nhà xuất bản...),
`can_read_online`, `detail_url`.

Thư mục `data/` không được commit vào git (xem `.gitignore`) vì đây là dữ
liệu crawl ra, có thể khá lớn và cần crawl lại theo thời gian thực để cập
nhật — không phải mã nguồn.

## Về việc tải nội dung sách ("--download-pdf")

Trang đọc của stbook.vn phục vụ nội dung sách dưới dạng ảnh scan độ phân
giải rất cao — mỗi trang ghép từ 4 ảnh PNG (~3 MB/ảnh gốc). Crawler tự
động thu nhỏ ảnh (mặc định cạnh dài tối đa 2000px) và nén JPEG trước khi
ghép thành PDF, nên một cuốn sách trên thực tế nặng khoảng **200-300
KB/trang** (đã test thật: sách 35 trang → file PDF 8,5 MB, chữ rõ nét).

- Tính năng này **tắt theo mặc định**, phải bật rõ ràng bằng `--download-pdf`.
- Chỉ áp dụng cho sách ghi "Bản điện tử: Miễn phí" *và* có nút "Xem ngay"
  (đọc được online, không cần app riêng) — sách có giá thì không thể lấy
  được nội dung bằng cách này.
- **Không giới hạn số trang theo mặc định** — tải trọn cuốn sách. Dùng
  `--max-pages N` nếu chỉ muốn một bản xem trước.
- **Tốc độ**: mỗi trang cần 4 request tải ảnh; trên thực tế đo được
  khoảng 6-7 giây/trang (server của NXB khá chậm). Một cuốn "Toàn tập"
  900 trang có thể mất **7-8 tiếng** để tải xong — hãy ước lượng thời
  gian trước khi chạy `--download-pdf` cho cả một danh mục lớn.
- Kết quả lưu tại `data/<slug>/content/<product_id>.pdf`; ảnh từng trang
  chỉ là file tạm và bị xoá sau khi ghép xong (giữ lại bằng
  `--keep-page-images` nếu cần).
- Đây vẫn là nội dung có bản quyền của NXB Chính trị Quốc gia Sự thật dù
  được ghi "miễn phí" để đọc online; hãy cân nhắc mục đích sử dụng (cá
  nhân/nghiên cứu) trước khi tải số lượng lớn hoặc toàn bộ catalog.

## Cấu trúc mã nguồn

```
src/stbook_crawler/
  client.py          # HTTP session có rate-limit + retry
  categories.py       # danh sách 15 danh mục cố định
  parse_category.py   # parse trang danh sách sách theo danh mục (có phân trang)
  parse_detail.py     # parse trang chi tiết 1 sách
  content.py           # tải + ghép ảnh các trang xem thử
  storage.py            # ghi JSON ra data/<slug>/books.json và all_books.json
  main.py               # CLI điều phối toàn bộ
```
