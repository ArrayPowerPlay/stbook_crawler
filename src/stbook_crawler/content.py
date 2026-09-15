"""Tải nội dung xem-thử (preview) của các sách điện tử "Miễn phí".

QUAN TRỌNG VỀ GIỚI HẠN: mỗi trang sách trên trình đọc của stbook.vn được
ghép từ 4 ảnh PNG độ phân giải rất cao (~3 MB/ảnh, tổng ~12 MB/trang).
Một số đầu sách (ví dụ các bộ "Toàn tập") có tới hàng nghìn trang, tức là
tải trọn một cuốn có thể tốn hàng chục GB. Vì vậy module này CHỈ tải một
số trang đầu tiên theo giới hạn `max_pages` (mặc định 10) cho mỗi cuốn —
đủ để có một bản xem trước, không tải toàn bộ nội dung sách. Muốn tải
nhiều hơn, truyền `max_pages` lớn hơn khi gọi `download_preview_pages`
(hoặc cờ --max-pages trên CLI), nhưng cần cân nhắc dung lượng ổ đĩa và
tôn trọng bản quyền nội dung của NXB.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from .client import RateLimitedSession

DEFAULT_MAX_PAGES = 10


def download_preview_pages(
    session: RateLimitedSession,
    product_code: str,
    out_dir: Path,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[Path]:
    """Tải tối đa `max_pages` trang đầu của sách, ghép 4 mảnh mỗi trang
    thành 1 ảnh JPEG hoàn chỉnh, lưu vào `out_dir`.

    Trả về danh sách đường dẫn các file ảnh đã lưu thành công. Nếu một
    trang không tải được (sách không thực sự mở được online, hết trang,
    lỗi mạng...) thì dừng vòng lặp tại đó — coi như đã hết nội dung khả
    dụng, không coi là lỗi nghiêm trọng.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for page in range(1, max_pages + 1):
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
        out_path = out_dir / f"page_{page:04d}.jpg"
        page_image.convert("RGB").save(out_path, "JPEG", quality=85)
        saved.append(out_path)

    return saved


def _stitch_quadrants(tiles: list[Image.Image]) -> Image.Image:
    """Ghép 4 ảnh góc (trên-trái, dưới-trái, trên-phải, dưới-phải) thành
    một ảnh trang hoàn chỉnh.

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
