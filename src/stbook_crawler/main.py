"""Điểm vào (entrypoint) chính của crawler stbook.vn.

Cách dùng cơ bản (crawl toàn bộ site, chỉ lấy metadata):

    python -m stbook_crawler.main

Các tuỳ chọn thường dùng:

    --category <slug>        chỉ crawl 1 danh mục (có thể lặp lại nhiều lần)
    --skip-detail             không gọi trang chi tiết (nhanh hơn, ít dữ liệu hơn)
    --download-covers         tải ảnh bìa về data/<slug>/covers/
    --fetch-content            tải thử vài trang đầu của các sách "Miễn phí"
    --max-pages N              số trang tối đa tải cho mỗi sách khi --fetch-content (mặc định 10)
    --delay SECONDS             độ trễ giữa các request (mặc định 0.8s)
    --out DIR                   thư mục ghi dữ liệu (mặc định ./data)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

from .categories import CATEGORIES, Category
from .client import RateLimitedSession
from .content import DEFAULT_MAX_PAGES, download_preview_pages
from .parse_category import fetch_category_books
from .parse_detail import fetch_book_detail
from .storage import book_record, category_dir_for, write_all_books, write_category_books

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stbook_crawler")


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
        "--fetch-content",
        action="store_true",
        help="Thử tải một số trang xem-trước của các sách ghi 'Miễn phí' và có thể đọc online.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Số trang tối đa tải mỗi sách khi dùng --fetch-content (mặc định {DEFAULT_MAX_PAGES}).",
    )
    parser.add_argument("--delay", type=float, default=0.8, help="Độ trễ (giây) giữa các request.")
    parser.add_argument("--out", type=Path, default=Path("data"), help="Thư mục ghi dữ liệu.")
    return parser.parse_args(argv)


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

            if args.fetch_content and item.product_code and _is_free_readable(item, detail):
                _fetch_content(session, args.out, category, item, args.max_pages)

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


def _fetch_content(
    session: RateLimitedSession, out_dir: Path, category: Category, item, max_pages: int
) -> None:
    content_dir = category_dir_for(out_dir, category) / "content" / item.product_id
    if content_dir.exists() and any(content_dir.iterdir()):
        return  # đã tải trước đó, không tải lại
    try:
        download_preview_pages(session, item.product_code, content_dir, max_pages=max_pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("  Lỗi tải nội dung sách %s: %s", item.product_id, exc)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    crawl(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
