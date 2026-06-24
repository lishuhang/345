const { chromium } = require('playwright');
const fs = require('fs');
const channels = JSON.parse(fs.readFileSync('./work/xuexi_m3u8_urls.json', 'utf8'));
const results = {};
const BATCH = 5;

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
  
  const keys = Object.keys(channels);
  for (let i = 0; i < keys.length; i += BATCH) {
    const batch = keys.slice(i, i + BATCH);
    console.log(`Batch ${Math.floor(i/BATCH)+1}: ${batch.map(k => channels[k].name).join(', ')}`);
    
    const promises = batch.map(async (key) => {
      const ch = channels[key];
      const page = await ctx.newPage();
      let m3u8Url = null;
      page.on('request', req => {
        const u = req.url();
        if (u.includes('live-pc.xuexi.cn') && u.includes('.m3u8') && u.includes('auth_key=')) {
          m3u8Url = u;
        }
      });
      try {
        await page.goto(`https://www.xuexi.cn/xxqg.html?id=${ch.id}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(5000);
        if (m3u8Url) {
          const u = new URL(m3u8Url);
          results[key] = { name: ch.name, id: ch.id, baseUrl: ch.fullUrl, host: u.host, path: u.pathname, fullUrl: m3u8Url };
          console.log(`  ✓ ${ch.name}`);
        } else {
          console.log(`  ✗ ${ch.name}`);
        }
      } catch (e) { console.log(`  ERR ${ch.name}: ${e.message}`); }
      await page.close();
    });
    
    await Promise.all(promises);
    // Save checkpoint
    fs.writeFileSync('./work/xuexi_m3u8_authed.json', JSON.stringify(results, null, 2));
  }
  
  await browser.close();
  fs.writeFileSync('./work/xuexi_m3u8_authed.json', JSON.stringify(results, null, 2));
  console.log(`\nSaved ${Object.keys(results).length} channels`);
})();
