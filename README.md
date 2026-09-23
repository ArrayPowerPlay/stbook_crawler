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

Dùng [uv](https://docs.astral.sh/uv/) để cài đặt (đọc `pyproject.toml` +
`uv.lock`):

```bash
uv sync
```

Sau đó chạy lệnh qua `uv run`, ví dụ `uv run python -m stbook_crawler.main`
— hoặc `source .venv/bin/activate` rồi chạy `python` như bình thường.

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

# Chỉnh số request tải nội dung sách chạy song song (mặc định 8)
python -m stbook_crawler.main --download-pdf --workers 8
```

Chạy `python -m stbook_crawler.main --help` để xem đầy đủ các cờ.

`--download-pdf` cần trang chi tiết để biết số trang mỗi sách (không dùng
được cùng `--skip-detail`). Việc lấy metadata (danh mục, chi tiết) vẫn
nghỉ 0.8 giây giữa hai request theo mặc định (`--delay` để chỉnh), tự
động thử lại khi gặp lỗi tạm thời — riêng việc tải nội dung PDF chạy
song song, xem phần bên dưới.

## Chạy full trên server GPU (Run:ai / JupyterLab)

Crawler không dùng GPU. Nhưng workspace Jupyter trên cluster Run:ai sẽ
**tự bị dừng nếu GPU nhàn rỗi quá lâu**, kéo theo crawler chết giữa
chừng mà không để lại log lỗi nào. Vì vậy trên server này phải chạy
crawler qua `scripts/run_with_gpu_keepalive.sh`. Script này chạy nền 2
tiến trình:

- **crawler** (`python -m stbook_crawler.main` với các cờ bạn truyền vào),
- **tiến trình giữ GPU** (`scripts/gpu_keepalive.py`): cứ 10 phút nhân
  một ma trận nhỏ trên GPU để Run:ai không coi GPU là nhàn rỗi. Tiến
  trình này cần `torch`, đã có sẵn trong dependency của dự án.

Cả hai chạy nền bằng `nohup`, nên đóng terminal/tab Jupyter vẫn không
sao. Khi crawler xong (hoặc bị dừng), tiến trình giữ GPU tự tắt theo.

### Các bước chạy

```bash
cd <thư mục repo>
git pull
uv sync                        # cài dependency, gồm cả torch bản CUDA (vài GB, lần đầu hơi lâu)
source .venv/bin/activate      # BẮT BUỘC: script gọi `python` của môi trường đang kích hoạt
./scripts/run_with_gpu_keepalive.sh --download-pdf
```

Có thể truyền thêm các cờ khác như khi chạy trực tiếp, ví dụ
`./scripts/run_with_gpu_keepalive.sh --download-pdf --category kinh-dien`.

### Kiểm tra đã chạy đúng chưa

```bash
pgrep -af "stbook_crawler.main|gpu_keepalive"   # phải thấy CẢ 2 tiến trình
nvidia-smi                                        # phải thấy 1 tiến trình python đang chiếm GPU
tail -f logs/crawl_output.log                     # xem tiến độ crawl (Ctrl+C chỉ tắt việc xem log)
```

- Nếu `pgrep` chỉ thấy crawler mà không thấy `gpu_keepalive`, xem lỗi
  trong `logs/gpu_keepalive.log`. Lỗi hay gặp là `No module named 'torch'`
  do quên `source .venv/bin/activate` hoặc chưa `uv sync`. Khi đó GPU
  vẫn nhàn rỗi và workspace sẽ lại bị dừng giữa chừng. Hãy dừng crawler
  (xem mục bên dưới) rồi chạy lại cho đúng.
- `logs/gpu_keepalive.log` có thể nhiều giờ sau mới hiện dòng
  "nhịp GPU OK", vì Python gom output lại rồi mới ghi ra file khi chạy
  nền. Muốn biết tiến trình giữ GPU còn sống thì dùng `nvidia-smi` hoặc
  `pgrep`, đừng dựa vào file log này.
- Cảnh báo `Failed to initialize NumPy: No module named 'numpy'` trong
  log là vô hại.

### Nếu workspace vẫn bị dừng / khởi động lại

Mở lại workspace rồi chạy lại **đúng các bước trên**. Crawler tự bỏ qua
những sách đã tải xong PDF và làm tiếp từ chỗ dừng. Có thể xem thời
điểm và lý do workspace bị dừng trong giao diện Run:ai (Workloads →
workspace → Event history).

## Dừng crawler đang chạy

Dừng lúc nào cũng được, không mất dữ liệu đã crawl: chạy lại **đúng lệnh
cũ** là crawler tự tiếp tục từ chỗ dừng (xem mục "Resume" trong
[`main.py`](src/stbook_crawler/main.py)). Chỉ cuốn sách đang tải dở lúc
dừng là phải tải lại từ đầu.

### Crawler chạy trực tiếp trong terminal (foreground)

Bấm **Ctrl+C**, nhưng cần biết khi đang tải PDF (`--download-pdf`):

- **Ctrl+C lần 1**: crawler nhận lệnh nhưng vẫn **tải cho xong cuốn sách
  đang tải dở** rồi mới dừng. Với sách dày (vd. các bộ "Toàn tập" trong
  danh mục Kinh điển) việc này có thể mất 15-30 phút, trông như bị treo.
- **Bấm Ctrl+C thêm 2 lần nữa** (tổng cộng 3 lần, cách nhau 1-2 giây) để
  dừng ngay. Terminal có thể in ra vài dòng `Traceback`/`KeyboardInterrupt`,
  không sao cả.

Nếu không dùng `--download-pdf` thì chỉ cần Ctrl+C 1 lần.

### Crawler chạy nền (qua `scripts/run_with_gpu_keepalive.sh` hoặc `nohup`)

Lúc này **Ctrl+C trong terminal không dừng được crawler**. Nếu đang xem
log bằng `tail -f logs/crawl_output.log`, Ctrl+C chỉ tắt lệnh `tail`, còn
crawler vẫn chạy tiếp. Muốn dừng thì dùng `kill`:

```bash
# 1. Xem crawler có đang chạy không (in ra PID + lệnh)
pgrep -af stbook_crawler.main

# 2. Dừng crawler (dừng ngay, kể cả khi đang tải PDF)
pkill -f stbook_crawler.main

# 3. Kiểm tra lại: không in ra gì nghĩa là đã dừng hẳn
pgrep -af stbook_crawler.main

# Nếu sau vài giây vẫn còn thì buộc dừng:
pkill -9 -f stbook_crawler.main
```

Khi crawler dừng, `run_with_gpu_keepalive.sh` tự tắt luôn tiến trình giữ
GPU. Nếu vẫn còn (kiểm tra bằng `pgrep -af gpu_keepalive`) thì tắt tay:

```bash
pkill -f gpu_keepalive.py
```

Lưu ý: nếu `kill` trúng đúng lúc crawler đang ghi file PDF ra đĩa (chỉ
mất vài giây ở cuối mỗi cuốn), file PDF đó có thể bị hỏng mà lần chạy
sau vẫn coi là đã tải xong. Nếu nghi ngờ, xoá file PDF mới nhất trong
`data/<slug>/content/` trước khi chạy lại.

### Log `WARNING Retrying ... Read timed out` có phải lỗi không?

Không. Đó là thư viện HTTP báo server stbook.vn trả lời chậm quá 30 giây
và **đang tự thử lại** (`total=4` là còn 4 lần thử). Crawler vẫn chạy
bình thường. Thanh tiến trình (`kinh-dien: 41%| 47/114 ...`) chỉ nhảy
khi tải xong **trọn một cuốn**, nên với sách dày có thể đứng yên 15-30
phút mà không có dòng log mới nào.

## Kết quả đầu ra

```
data/
  kinh-dien/
    books.json          # toàn bộ sách của riêng danh mục "Kinh điển"
    covers/              # ảnh bìa, nếu bật --download-covers
    content/<id>.pdf      # PDF trọn cuốn, nếu bật --download-pdf
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

Trang đọc của stbook.vn phục vụ nội dung sách dưới dạng ảnh — mỗi trang
ghép từ 4 ảnh PNG. Crawler tự động thu nhỏ ảnh (mặc định cạnh dài tối đa
2000px) và nén JPEG trước khi ghép thành PDF, dung lượng thực tế đo
được khoảng **10-160 KB/trang** tuỳ độ phức tạp trang.

- Tính năng này **tắt theo mặc định**, phải bật rõ ràng bằng `--download-pdf`.
- Chỉ áp dụng cho sách ghi "Bản điện tử: Miễn phí" *và* có nút "Xem ngay"
  (đọc được online, không cần app riêng) — sách có giá thì không thể lấy
  được nội dung bằng cách này. Một số ít sách gắn nhãn "đọc được" nhưng
  server thực ra báo "Sách đang cập nhật" (đo được ~2,5% trên mẫu ngẫu
  nhiên) — trường hợp này bị bỏ qua tự động, có log cảnh báo.
- **Không giới hạn số trang theo mặc định** — tải trọn cuốn sách (dựa
  vào field "Số trang" ở trang chi tiết). Dùng `--max-pages N` nếu chỉ
  muốn một bản xem trước.
- **Tải song song** (`--workers`, mặc định 8): mỗi trang cần 4 request
  ảnh, tất cả được xếp vào một hàng đợi chung và xử lý bởi `--workers`
  luồng cùng lúc. Đo thực tế trên server stbook.vn cho thấy tốc độ phản
  hồi đạt trần ở khoảng **~8 request/giây** bất kể mở bao nhiêu kết nối
  cùng lúc (đã thử 4/8/16/24/32 luồng — từ 8 luồng trở lên không còn
  nhanh hơn) — 8 là điểm cân bằng tốt nhất, không cần chỉnh trừ khi có
  lý do cụ thể.
- Với tốc độ ~8 request/giây, tải trọn **toàn bộ ~826 sách miễn phí của
  site (~495.000 trang)** ước tính mất khoảng **2,5-3 ngày chạy liên
  tục** — so với ~29 ngày nếu tải tuần tự từng ảnh một. Một cuốn "Toàn
  tập" 900 trang mất khoảng 30 phút.
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
  content.py           # tải song song + ghép ảnh các trang, xuất PDF
  storage.py            # ghi JSON ra data/<slug>/books.json và all_books.json
  main.py               # CLI điều phối toàn bộ
```
