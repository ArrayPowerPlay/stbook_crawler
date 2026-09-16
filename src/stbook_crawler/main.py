"""Điểm vào (entrypoint) chính của crawler stbook.vn.

Cách dùng cơ bản (crawl toàn bộ site, chỉ lấy metadata):

    python -m stbook_crawler.main

Các tuỳ chọn thường dùng:

    --category <slug>        chỉ crawl 1 danh mục (có thể lặp lại nhiều lần)
    --skip-detail             không gọi trang chi tiết (nhanh hơn, ít dữ liệu hơn;
                               không dùng được cùng --download-pdf)
    --download-covers         tải ảnh bìa về data/<slug>/covers/
    --download-pdf              tải TOÀN BỘ nội dung các sách "Miễn phí" đọc được
                                 online, ghép thành file PDF tại data/<slug>/content/<id>.pdf
    --max-pages N                giới hạn số trang tải mỗi sách khi --download-pdf
                                 (mặc định: không giới hạn, tải hết sách)
    --workers N                   số request tải nội dung sách chạy song song
                                 (mặc định 8 — đo thực tế cho thấy server không
                                 phản hồi nhanh hơn dù mở nhiều kết nối hơn)
    --keep-page-images           giữ lại ảnh từng trang sau khi đã ghép PDF (mặc định xoá)
    --delay SECONDS               độ trễ giữa các request lấy metadata (mặc định 0.8s)
    --out DIR                     thư mục ghi dữ liệu (mặc định ./data)
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

from .categories import CATEGORIES, Category
from .client import RateLimitedSession, build_bulk_session
from .content import DEFAULT_WORKERS, assemble_pdf, download_book_pages
from .parse_category import fetch_category_books
from .parse_detail import BookDetail, fetch_book_detail
from .storage import book_record, category_dir_for, write_all_books, write_category_books

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stbook_crawler")

_PAGE_COUNT_RE = re.compile(r"\d+")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl sách trên stbook.vn theo danh mục.")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        metavar="SLUG",
        help="Chỉ crawl danh mục có slug này (lặp lại cờ để chọn nhiều danh mục).",
    )
    parser.add_argument(
        "--skip-detail",
        action="store_true",
        help="Bỏ qua việc gọi trang chi tiết từng sách (nhanh hơn, thiếu mô tả/tác giả đầy đủ).",
    )
    parser.add_argument(
        "--download-covers",
        action="store_true",
        help="Tải ảnh bìa sách về data/<slug>/covers/.",
    )
    parser.add_argument(
        "--download-pdf",
        action="store_true",
        help="Tải toàn bộ nội dung các sách 'Miễn phí' đọc được online, ghép thành PDF.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Giới hạn số trang tải mỗi sách khi dùng --download-pdf (mặc định: không giới hạn).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Số request tải nội dung sách chạy song song (mặc định {DEFAULT_WORKERS}).",
    )
    parser.add_argument(
        "--keep-page-images",
        action="store_true",
        help="Giữ lại ảnh JPEG từng trang sau khi đã ghép thành PDF (mặc định xoá để tiết kiệm ổ đĩa).",
    )
    parser.add_argument("--delay", type=float, default=0.8, help="Độ trễ (giây) giữa các request lấy metadata.")
    parser.add_argument("--out", type=Path, default=Path("data"), help="Thư mục ghi dữ liệu.")
    args = parser.parse_args(argv)

    if args.download_pdf and args.skip_detail:
        parser.error(
            "--download-pdf cần trang chi tiết để biết số trang mỗi sách, "
            "không dùng được cùng --skip-detail."
        )

    return args


def select_categories(slugs: list[str] | None) -> list[Category]:
    if not slugs:
        return CATEGORIES
    wanted = set(slugs)
    selected = [c for c in CATEGORIES if c.slug in wanted]
    missing = wanted - {c.slug for c in selected}
    if missing:
        log.warning("Không tìm thấy danh mục với slug: %s", ", ".join(sorted(missing)))
    return selected


def crawl(args: argparse.Namespace) -> None:
    session = RateLimitedSession(delay_seconds=args.delay)
    bulk_session = build_bulk_session(pool_size=args.workers) if args.download_pdf else None
    categories = select_categories(args.categories)
    args.out.mkdir(parents=True, exist_ok=True)

    all_books: list[dict] = []

    for category in categories:
        log.info("=== Danh mục: %s (p_id=%s) ===", category.name, category.p_id)
        list_items = fetch_category_books(session, category)
        log.info("  Tìm thấy %d sách.", len(list_items))

        category_books: list[dict] = []
        for item in tqdm(list_items, desc=category.slug, unit="sách"):
            detail = None
            if not args.skip_detail:
                try:
                    detail = fetch_book_detail(session, item.product_id)
                except Exception as exc:  # noqa: BLE001 - crawler phải bền vững, không dừng cả job
                    log.warning("  Lỗi lấy chi tiết sách %s: %s", item.product_id, exc)

            record = book_record(item, detail)
            category_books.append(record)

            if args.download_covers and item.cover_url:
                _download_cover(session, args.out, category, item)

            if args.download_pdf and item.product_code and _is_free_readable(item, detail):
                _download_pdf(
                    bulk_session, args.out, category, item, detail, args.max_pages, args.workers, args.keep_page_images
                )

        write_category_books(args.out, category, category_books)
        all_books.extend(category_books)

    write_all_books(args.out, all_books)
    log.info("Hoàn tất. Tổng số sách: %d", len(all_books))


def _is_free_readable(item, detail) -> bool:
    is_free = (item.price_ebook or "").strip().lower() == "miễn phí"
    can_read = detail.can_read_online if detail is not None else True
    return is_free and can_read


def _download_cover(session: RateLimitedSession, out_dir: Path, category: Category, item) -> None:
    covers_dir = category_dir_for(out_dir, category) / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    dest = covers_dir / f"{item.product_id}.png"
    if dest.exists():
        return
    try:
        response = session.get(item.cover_url)
        dest.write_bytes(response.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("  Lỗi tải ảnh bìa sách %s: %s", item.product_id, exc)


def _parse_page_count(detail: BookDetail | None) -> int | None:
    """Đọc số trang từ field "Số trang" ở trang chi tiết sách (ví dụ "992 trang")."""
    if detail is None:
        return None
    raw = detail.info.get("Số trang")
    if not raw:
        return None
    match = _PAGE_COUNT_RE.search(raw)
    return int(match.group()) if match else None


def _download_pdf(
    bulk_session,
    out_dir: Path,
    category: Category,
    item,
    detail: BookDetail | None,
    max_pages: int | None,
    workers: int,
    keep_page_images: bool,
) -> None:
    content_dir = category_dir_for(out_dir, category) / "content"
    pdf_path = content_dir / f"{item.product_id}.pdf"
    if pdf_path.exists():
        return  # đã tải trước đó, không tải lại

    num_pages = _parse_page_count(detail)
    if num_pages is None:
        log.warning("  Bỏ qua sách %s: không xác định được số trang.", item.product_id)
        return
    if max_pages is not None:
        num_pages = min(num_pages, max_pages)

    pages_dir = content_dir / f"{item.product_id}_pages"
    try:
        pages = download_book_pages(bulk_session, item.product_code, pages_dir, num_pages, max_workers=workers)
        assemble_pdf(pages, pdf_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("  Lỗi tải nội dung sách %s: %s", item.product_id, exc)
    finally:
        if not keep_page_images and pages_dir.exists():
            shutil.rmtree(pages_dir)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    crawl(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
