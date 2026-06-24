#!/bin/bash
set -e
cd /workspace

echo "=== Step 1: Refresh YSP URLs ==="
rm -f work/ysp_checkpoint.json
node scripts/gen_ysp_urls3.js > /tmp/ysp_gen.log 2>&1 &
YSP_PID=$!
# Auto-restart if died
for i in $(seq 1 30); do
  sleep 30
  if grep -q "Done:" /tmp/ysp_gen.log 2>/dev/null; then
    echo "YSP URLs generated"
    break
  fi
  if ! kill -0 $YSP_PID 2>/dev/null; then
    if ! grep -q "Done:" /tmp/ysp_gen.log 2>/dev/null; then
      echo "YSP process died, restarting..."
      node scripts/gen_ysp_urls3.js >> /tmp/ysp_gen.log 2>&1 &
      YSP_PID=$!
    fi
  fi
done

echo "=== Step 2: Refresh xuexi URLs ==="
rm -f work/xuexi_checkpoint.json
node scripts/gen_xuexi_fast.js > /tmp/xuexi_gen.log 2>&1 &
XUEXI_PID=$!
for i in $(seq 1 15); do
  sleep 30
  if grep -q "Saved" /tmp/xuexi_gen.log 2>/dev/null; then
    echo "xuexi URLs generated"
    break
  fi
  if ! kill -0 $XUEXI_PID 2>/dev/null; then
    if ! grep -q "Saved" /tmp/xuexi_gen.log 2>/dev/null; then
      echo "xuexi process died, restarting..."
      node scripts/gen_xuexi_fast.js >> /tmp/xuexi_gen.log 2>&1 &
      XUEXI_PID=$!
    fi
  fi
done

echo "=== Step 3: Build Worker ==="
python3 scripts/build_v210_blind.py

echo "=== Step 4: Apply segment fix ==="
python3 scripts/apply_segment_fix.py

echo "=== Step 5: Deploy ==="
cp work/worker_v210_blind.js work/worker.js
python3 scripts/deploy_worker.py

echo "=== Step 6: Verify ==="
sleep 5
STATUS=$(curl -s "https://iptv345.lishuhang.workers.dev/" | head -1)
echo "Status: $STATUS"

echo "=== Done ==="
