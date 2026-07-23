#!/usr/bin/env python3
"""Build v2.8+ysp+xuexi blind worker.
- Base: v2.8-blind.js (with /health, /refresh, broken cache, EXT-X-PROGRAM-DATE-TIME)
- Update YSP_CATALOG: merge fresh URLs into existing catalog (preserve all 46 channels,
  update fullUrl for successfully refreshed ones)
- Insert xuexi handlers + routes + health check
"""
import json, re, os
from urllib.parse import urlparse

# Read base worker (v2.8-blind)
with open('./work/worker_v26_blind.js', 'r') as f:
    code = f.read()
print(f'Base worker: {len(code)} bytes')

# Extract existing YSP_CATALOG (46 channels with old URLs)
ysp_catalog_match = re.search(r"const YSP_CATALOG = JSON\.parse\('(.*?)'\);", code, re.DOTALL)
if not ysp_catalog_match:
    print('ERROR: YSP_CATALOG not found')
    exit(1)
existing_ysp_str = ysp_catalog_match.group(1).replace("\\'", "'").replace("\\\\", "\\")
existing_ysp = json.loads(existing_ysp_str)
print(f'Existing YSP_CATALOG: {len(existing_ysp)} channels')

# Load fresh YSP URLs
ysp_fresh = {}
if os.path.exists('./work/ysp_m3u8_urls.json'):
    with open('./work/ysp_m3u8_urls.json', 'r') as f:
        ysp_fresh = json.load(f)
    print(f'Fresh YSP URLs: {len(ysp_fresh)} channels')

# Merge: update fullUrl (and host/path) for refreshed channels, keep others as-is
updated = 0
for key, fresh_data in ysp_fresh.items():
    if key in existing_ysp:
        full_url = fresh_data['fullUrl']
        parsed = urlparse(full_url)
        existing_ysp[key]['fullUrl'] = full_url
        existing_ysp[key]['host'] = parsed.netloc
        existing_ysp[key]['path'] = parsed.path
        existing_ysp[key]['pid'] = fresh_data.get('pid', existing_ysp[key].get('pid', ''))
        updated += 1
print(f'Updated {updated}/{len(existing_ysp)} channels with fresh URLs')

# Write back YSP_CATALOG
new_ysp_json = json.dumps(existing_ysp, ensure_ascii=False, separators=(',', ':'))
new_ysp_json_escaped = new_ysp_json.replace('\\', '\\\\').replace("'", "\\'")
new_ysp_line = f"const YSP_CATALOG = JSON.parse('{new_ysp_json_escaped}');"
code = code[:ysp_catalog_match.start()] + new_ysp_line + code[ysp_catalog_match.end():]
print('1. Updated YSP_CATALOG')

# Load xuexi URLs
xuexi_urls = {}
if os.path.exists('./work/xuexi_m3u8_authed.json'):
    with open('./work/xuexi_m3u8_authed.json', 'r') as f:
        xuexi_urls = json.load(f)
    print(f'Loaded xuexi: {len(xuexi_urls)} channels')

xuexi_catalog = {}
for key, data in xuexi_urls.items():
    xuexi_catalog[key] = {
        'name': data['name'],
        'id': data['id'],
        'host': data['host'],
        'path': data['path'],
        'fullUrl': data['fullUrl'],
    }
xuexi_json = json.dumps(xuexi_catalog, ensure_ascii=False, separators=(',', ':'))
xuexi_json_escaped = xuexi_json.replace('\\', '\\\\').replace("'", "\\'")

# Insert XUEXI_CATALOG after YSP_CACHE_TTL
xuexi_const = f"\n\n// XUEXI CATALOG\nconst XUEXI_CATALOG = JSON.parse('{xuexi_json_escaped}');\nconst XUEXI_CACHE = new Map();\nconst XUEXI_CACHE_TTL = 30 * 60 * 1000;\n"
ysp_ttl_end = code.find('const YSP_CACHE_TTL = 3 * 60 * 60 * 1000;')
if ysp_ttl_end >= 0:
    ysp_ttl_line_end = code.index('\n', ysp_ttl_end) + 1
    code = code[:ysp_ttl_line_end] + xuexi_const + code[ysp_ttl_line_end:]
    print(f'2. Inserted XUEXI_CATALOG ({len(xuexi_catalog)} channels)')
else:
    print('ERROR: YSP_CACHE_TTL not found')
    exit(1)

# Add xuexi handlers before MAIN ROUTER
router_marker = '// =================== MAIN ROUTER ==================='
xuexi_handlers = """
// =================== XUEXI HANDLERS ===================

async function handleXuexiM3u8(xuexiKey, request) {
  const ch = XUEXI_CATALOG[xuexiKey];
  if (!ch) return textResponse('Not found: ' + xuexiKey, 404);

  const cached = XUEXI_CACHE.get(xuexiKey);
  if (cached && Date.now() - cached.ts < XUEXI_CACHE_TTL) {
    try {
      const testResp = await fetch(cached.url, { method: 'HEAD', headers: { 'User-Agent': 'Mozilla/5.0' } });
      if (testResp.ok || testResp.status === 405) {
        const resp = await fetch(cached.url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        if (resp.ok) {
          const body = await resp.text();
          return rewriteXuexiM3u8(body, ch, request);
        }
      }
    } catch (e) {}
  }

  let resp;
  try {
    resp = await fetch(ch.fullUrl, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  } catch (e) {
    return textResponse('xuexi m3u8 fetch error: ' + e.message, 502);
  }

  if (resp.status === 403) {
    XUEXI_CACHE.delete(xuexiKey);
    triggerRefresh();
    return textResponse('xuexi m3u8 expired (403). Refresh triggered.', 502);
  }

  if (!resp.ok) return textResponse('xuexi m3u8 failed: ' + resp.status, 502);

  XUEXI_CACHE.set(xuexiKey, { url: ch.fullUrl, ts: Date.now() });
  const body = await resp.text();
  return rewriteXuexiM3u8(body, ch, request);
}

function rewriteXuexiM3u8(m3u8body, ch, request) {
  const myOrigin = new URL(request.url).origin;
  const basePath = ch.path.replace(/[^\\/]*$/, '');
  const rewritten = m3u8body.split('\\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    return myOrigin + '/xseg2/' + ch.host + basePath + trimmed;
  }).join('\\n');

  return new Response(rewritten, {
    status: 200,
    headers: {
      'Content-Type': 'application/vnd.apple.mpegurl',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'CDN-Cache-Control': 'no-store',
    },
  });
}

async function handleXseg2(fullPath, request) {
  const slashIdx = fullPath.indexOf('/');
  if (slashIdx < 0) return textResponse('Invalid xseg2 path', 400);
  const host = fullPath.substring(0, slashIdx);
  const pathAndQuery = fullPath.substring(slashIdx);
  const segUrl = 'https://' + host + pathAndQuery;

  const cacheUrl = new URL('https://xseg-cache.iptv345.local/' + fullPath.slice(0, 100));
  const cacheKey = new Request(cacheUrl, { method: 'GET' });
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) {
    return new Response(cached.body, {
      status: 200,
      headers: { 'Content-Type': 'video/mp2t', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=600', 'X-Cache': 'HIT' },
    });
  }

  let upstream;
  try {
    upstream = await fetch(segUrl, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  } catch (e) {
    return textResponse('xuexi segment error: ' + e.message, 502);
  }

  if (!upstream.ok) return textResponse('xuexi segment failed: ' + upstream.status, 502);

  const body = await upstream.arrayBuffer();
  const resp = new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'video/mp2t', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=600', 'X-Cache': 'MISS' },
  });
  try { cache.put(cacheKey, resp.clone()).catch(() => {}); } catch (e) {}
  return resp;
}

"""
code = code.replace(router_marker, xuexi_handlers + router_marker)
print('3. Inserted xuexi handlers')

# Add xuexi routes before /cat/<tid>
xuexi_routes = """    // /xuexi_<id>.m3u8
    const xuexiMatch = path.match(/^\\/xuexi_[a-f0-9]+\\.m3u8$/);
    if (xuexiMatch) {
      return handleXuexiM3u8(xuexiMatch[0].substring(1).replace('.m3u8',''), request);
    }

    // /xseg2/<host>/<path>
    const xseg2Match = path.match(/^\\/xseg2\\/(.+)$/);
    if (xseg2Match) {
      return handleXseg2(xseg2Match[1] + url.search, request);
    }

"""
cat_route = "    // /cat/<tid>"
code = code.replace(cat_route, xuexi_routes + cat_route)
print('4. Inserted xuexi routes')

# Update handleHome with xuexi health check
old_status = "  statusLine += okYsp ? 'ysp ok' : 'ysp error'; if (!okYsp) allOk = false;"
new_status = """  statusLine += okYsp ? 'ysp ok' : 'ysp error'; if (!okYsp) allOk = false;
  statusLine += '; ';
  let okXuexi = true;
  try {
    const xkeys = Object.keys(XUEXI_CATALOG);
    log('--- xuexi check ---');
    log('OK xuexi catalog: ' + xkeys.length + ' channels');
    const firstXKey = xkeys[0];
    const xch = XUEXI_CATALOG[firstXKey];
    log('Testing xuexi m3u8 for ' + firstXKey + ' (' + xch.name + ')...');
    const xresp = await fetch(xch.fullUrl, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    if (xresp.ok) { const xbody = await xresp.text(); if (xbody.includes('#EXTM3U')) { log('OK xuexi m3u8 fetched'); } else { okXuexi = false; log('FAIL xuexi m3u8: no #EXTM3U'); } }
    else { okXuexi = false; log('FAIL xuexi m3u8: status=' + xresp.status + ' (URL may have expired)'); }
  } catch (e) { okXuexi = false; log('FAIL xuexi: ' + e.message); }
  statusLine += okXuexi ? 'xuexi ok' : 'xuexi error'; if (!okXuexi) allOk = false;"""
code = code.replace(old_status, new_status)
print('5. Updated handleHome with xuexi health check')

with open('./work/worker_v28_full_blind.js', 'w') as f:
    f.write(code)
print(f'\nFinal worker: {len(code)} bytes')
print(f'  YSP: {len(existing_ysp)} channels ({updated} fresh)')
print(f'  xuexi: {len(xuexi_catalog)} channels')
