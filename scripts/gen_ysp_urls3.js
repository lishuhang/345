// Optimized: single page reuse + incremental save + checkpoint
const { chromium } = require('playwright');
const fs = require('fs');

const CHANNELS = [
  { name: 'CCTV1', pid: '600001859', type: 'c', idx: '01' },
  { name: 'CCTV2', pid: '600001800', type: 'c', idx: '02' },
  { name: 'CCTV3', pid: '600001801', type: 'c', idx: '03' },
  { name: 'CCTV4', pid: '600001814', type: 'c', idx: '04' },
  { name: 'CCTV5', pid: '600001818', type: 'c', idx: '05' },
  { name: 'CCTV5+', pid: '600001817', type: 'c', idx: '06' },
  { name: 'CCTV6', pid: '600108442', type: 'c', idx: '07' },
  { name: 'CCTV7', pid: '600004092', type: 'c', idx: '08' },
  { name: 'CCTV8', pid: '600001803', type: 'c', idx: '09' },
  { name: 'CCTV9', pid: '600004078', type: 'c', idx: '10' },
  { name: 'CCTV10', pid: '600001805', type: 'c', idx: '11' },
  { name: 'CCTV11', pid: '600001806', type: 'c', idx: '12' },
  { name: 'CCTV12', pid: '600001807', type: 'c', idx: '13' },
  { name: 'CCTV13', pid: '600001811', type: 'c', idx: '14' },
  { name: 'CCTV14', pid: '600001809', type: 'c', idx: '15' },
  { name: 'CCTV15', pid: '600001815', type: 'c', idx: '16' },
  { name: 'CCTV17', pid: '600001810', type: 'c', idx: '17' },
  { name: '北京卫视', pid: '600002309', type: 'w', idx: '01' },
  { name: '江苏卫视', pid: '600002521', type: 'w', idx: '02' },
  { name: '东方卫视', pid: '600002483', type: 'w', idx: '03' },
  { name: '浙江卫视', pid: '600002520', type: 'w', idx: '04' },
  { name: '湖南卫视', pid: '600002475', type: 'w', idx: '05' },
  { name: '湖北卫视', pid: '600002508', type: 'w', idx: '06' },
  { name: '广东卫视', pid: '600002485', type: 'w', idx: '07' },
  { name: '广西卫视', pid: '600002509', type: 'w', idx: '08' },
  { name: '黑龙江卫视', pid: '600002498', type: 'w', idx: '09' },
  { name: '海南卫视', pid: '600002506', type: 'w', idx: '10' },
  { name: '重庆卫视', pid: '600002531', type: 'w', idx: '11' },
  { name: '深圳卫视', pid: '600002481', type: 'w', idx: '12' },
  { name: '四川卫视', pid: '600002516', type: 'w', idx: '13' },
  { name: '河南卫视', pid: '600002525', type: 'w', idx: '14' },
  { name: '福建东南卫视', pid: '600002484', type: 'w', idx: '15' },
  { name: '贵州卫视', pid: '600002490', type: 'w', idx: '16' },
  { name: '江西卫视', pid: '600002503', type: 'w', idx: '17' },
  { name: '辽宁卫视', pid: '600002505', type: 'w', idx: '18' },
  { name: '安徽卫视', pid: '600002532', type: 'w', idx: '19' },
  { name: '河北卫视', pid: '600002493', type: 'w', idx: '20' },
  { name: '山东卫视', pid: '600002513', type: 'w', idx: '21' },
  { name: '天津卫视', pid: '600152137', type: 'w', idx: '22' },
  { name: '吉林卫视', pid: '600190405', type: 'w', idx: '23' },
  { name: '陕西卫视', pid: '600190400', type: 'w', idx: '24' },
  { name: '宁夏卫视', pid: '600190737', type: 'w', idx: '25' },
  { name: '内蒙古卫视', pid: '600190401', type: 'w', idx: '26' },
  { name: '云南卫视', pid: '600190402', type: 'w', idx: '27' },
  { name: '山西卫视', pid: '600190407', type: 'w', idx: '28' },
  { name: '青海卫视', pid: '600190406', type: 'w', idx: '29' },
  { name: '西藏卫视', pid: '600190403', type: 'w', idx: '30' },
  { name: '新疆卫视', pid: '600152138', type: 'w', idx: '31' },
];

const OUTPUT_FILE = './work/ysp_m3u8_urls.json';
const CHECKPOINT_FILE = './work/ysp_checkpoint.json';

// Load checkpoint
let results = {};
let startIdx = 0;
if (fs.existsSync(CHECKPOINT_FILE)) {
  try {
    const cp = JSON.parse(fs.readFileSync(CHECKPOINT_FILE, 'utf8'));
    results = cp.results || {};
    startIdx = cp.nextIdx || 0;
    console.log(`Resumed from checkpoint: idx=${startIdx}, captured=${Object.keys(results).length}`);
  } catch(e) {}
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    viewport: { width: 1400, height: 900 },
  });

  for (let i = startIdx; i < CHANNELS.length; i++) {
    const ch = CHANNELS[i];
    const key = `ysp${ch.type}${ch.idx}`;
    
    // Skip if already captured
    if (results[key]) {
      console.log(`[${i+1}/${CHANNELS.length}] ${ch.name} -> ${key} (already captured)`);
      continue;
    }

    console.log(`[${i+1}/${CHANNELS.length}] ${ch.name} (pid=${ch.pid}) -> ${key}...`);

    const page = await context.newPage();
    let capturedUrl = null;

    const responseHandler = async (res) => {
      if (res.url().includes('get_live_info')) {
        try {
          const body = JSON.parse(await res.text());
          if (body.data && body.data.playurl) {
            capturedUrl = body.data.playurl + body.data.extended_param;
          }
        } catch(e) {}
      }
    };
    page.on('response', responseHandler);

    try {
      await page.goto(`https://yangshipin.cn/tv/home?pid=${ch.pid}`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(5000);

      if (capturedUrl) {
        const urlObj = new URL(capturedUrl);
        results[key] = {
          name: ch.name,
          pid: ch.pid,
          fullUrl: capturedUrl,
          host: urlObj.host,
          path: urlObj.pathname,
          search: urlObj.search,
        };
        console.log(`  ✓ ${capturedUrl.slice(0, 80)}...`);
      } else {
        console.log(`  ✗ No m3u8 URL captured`);
      }
    } catch (e) {
      console.log(`  Error: ${e.message}`);
    }

    await page.close();

    // Checkpoint every 3 channels
    if ((i + 1) % 3 === 0 || i === CHANNELS.length - 1) {
      fs.writeFileSync(CHECKPOINT_FILE, JSON.stringify({ results, nextIdx: i + 1 }));
      fs.writeFileSync(OUTPUT_FILE, JSON.stringify(results, null, 2));
    }
  }

  await browser.close();

  // Final save
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(results, null, 2));
  try { fs.unlinkSync(CHECKPOINT_FILE); } catch(e) {}
  console.log(`\n=== Done: ${Object.keys(results).length}/${CHANNELS.length} channels captured ===`);

  // Generate list-ysp.txt
  const listLines = [];
  for (const ch of CHANNELS) {
    const key = `ysp${ch.type}${ch.idx}`;
    if (results[key]) {
      listLines.push(`${ch.name},https://iptv345.lishuhang.workers.dev/${key}.m3u8`);
    }
  }
  fs.writeFileSync('./work/list-ysp.txt', listLines.join('\n') + '\n');
  console.log(`Saved list-ysp.txt (${listLines.length} entries)`);
})();
