"""Tải nội dung đầy đủ của các sách điện tử "Miễn phí" và đóng gói thành PDF.

Mỗi trang sách trên trình đọc của stbook.vn được ghép từ 4 ảnh PNG độ
phân giải rất cao (gốc ~3500x5200px, ~3 MB/ảnh góc). Module này:

1. Tải lần lượt từng trang (dừng khi gặp trang không tải được — coi như
   đã hết sách), ghép 4 mảnh thành 1 ảnh trang hoàn chỉnh.
2. Thu nhỏ ảnh về `max_dimension` (mặc định 2000px cạnh dài) và nén JPEG
   để dung lượng hợp lý mà vẫn đọc rõ chữ — bản gốc không nén có thể nặng
   ~12 MB/trang, quá lớn để lưu trữ hàng loạt.
3. Ghép toàn bộ ảnh trang thành 1 file PDF duy nhất cho mỗi cuốn sách.

LƯU Ý VỀ QUY MÔ: một số đầu sách (ví dụ các bộ "Toàn tập") có tới hàng
nghìn trang. Với ảnh đã nén, mỗi trang ước tính ~200-500 KB, tức một
cuốn 900 trang có thể vẫn nặng 200-400 MB. Nếu tải nhiều cuốn/toàn bộ
danh mục, hãy ước lượng dung lượng ổ đĩa và thời gian trước khi chạy —
đây vẫn là nội dung có bản quyền của NXB, chỉ nên dùng cho mục đích cá
nhân/nghiên cứu hợp lý.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from .client import RateLimitedSession

DEFAULT_MAX_DIMENSION = 2000
DEFAULT_JPEG_QUALITY = 82


def download_book_pages(
    session: RateLimitedSession,
    product_code: str,
    out_dir: Path,
    max_pages: int | None = None,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> list[Path]:
    """Tải các trang của sách (từ trang 1), ghép + nén, lưu vào `out_dir`.

    `max_pages=None` nghĩa là tải cho đến khi hết sách (không giới hạn).
    Trả về danh sách đường dẫn ảnh trang đã lưu, theo đúng thứ tự trang.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    page = 1

    while max_pages is None or page <= max_pages:
        tiles: list[Image.Image] = []
        for quadrant in range(1, 5):
            image_name = f"img_short_{quadrant}{page}"
            url = f"/cbs20/download_preview/img.json/{product_code}/{image_name}/_READ"
            try:
                response = session.get(url)
            except Exception:
                break
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type:
                break
            tiles.append(Image.open(io.BytesIO(response.content)))

        if len(tiles) != 4:
            break  # Hết trang hoặc sách không mở được online -> dừng.

        page_image = _stitch_quadrants(tiles)
        page_image = _downscale(page_image, max_dimension)
        out_path = out_dir / f"page_{page:04d}.jpg"
        page_image.convert("RGB").save(out_path, "JPEG", quality=jpeg_quality)
        saved.append(out_path)
        page += 1

    return saved


def assemble_pdf(page_image_paths: list[Path], pdf_path: Path) -> Path | None:
    """Ghép danh sách ảnh trang (theo đúng thứ tự) thành 1 file PDF.

    Trả về đường dẫn PDF, hoặc None nếu danh sách ảnh rỗng (không có gì
    để ghép).
    """
    if not page_image_paths:
        return None
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.open(p).convert("RGB") for p in page_image_paths]
    first, rest = images[0], images[1:]
    first.save(pdf_path, "PDF", save_all=True, append_images=rest)
    return pdf_path


def _downscale(image: Image.Image, max_dimension: int) -> Image.Image:
    longest = max(image.size)
    if longest <= max_dimension:
        return image
    scale = max_dimension / longest
    new_size = (round(image.width * scale), round(image.height * scale))
    return image.resize(new_size, Image.LANCZOS)


def _stitch_quadrants(tiles: list[Image.Image]) -> Image.Image:
    """Ghép 4 ảnh góc thành một ảnh trang hoàn chỉnh.

    Thứ tự quadrant 1-4 suy ra từ CSS `.img_1`..`.img_4` của trình đọc:
    1 = trên-trái, 2 = trên-phải, 3 = dưới-trái, 4 = dưới-phải (lưới 2x2).
    """
    top_left, top_right, bottom_left, bottom_right = tiles
    w, h = top_left.size
    full = Image.new("RGB", (w * 2, h * 2))
    full.paste(top_left, (0, 0))
    full.paste(top_right, (w, 0))
    full.paste(bottom_left, (0, h))
    full.paste(bottom_right, (w, h))
    return full
