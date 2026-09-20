#!/usr/bin/env bash
# Chạy crawler (mọi tham số truyền vào script này sẽ được chuyển thẳng cho
# `python -m stbook_crawler.main`) song song với gpu_keepalive.py, cả hai
# chạy nền (nohup) để sống sót qua việc đóng terminal/tab Jupyter. Khi
# crawler chạy xong (hoặc bị dừng), gpu_keepalive tự động bị kill theo —
# không giữ GPU bận vô ích sau khi không còn cần nữa.
#
# Cách dùng (chạy từ thư mục gốc repo):
#   ./scripts/run_with_gpu_keepalive.sh --download-pdf
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p logs
nohup python -m stbook_crawler.main "$@" > logs/crawl_output.log 2>&1 &
CRAWLER_PID=$!
echo "Crawler đã chạy nền, PID=$CRAWLER_PID (log: logs/crawl_output.log)"

nohup python scripts/gpu_keepalive.py > logs/gpu_keepalive.log 2>&1 &
KEEPALIVE_PID=$!
echo "GPU keepalive đã chạy nền, PID=$KEEPALIVE_PID (log: logs/gpu_keepalive.log)"

(
  wait "$CRAWLER_PID" || true
  echo "Crawler đã dừng, tắt GPU keepalive (PID=$KEEPALIVE_PID)."
  kill "$KEEPALIVE_PID" 2>/dev/null || true
) > logs/watcher.log 2>&1 &

disown -a
echo "Xong. Cả 2 tiến trình chạy độc lập với terminal này, có thể đóng terminal an toàn."
