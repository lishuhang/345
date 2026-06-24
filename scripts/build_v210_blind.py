#!/usr/bin/env python3
"""Build v2.10 blind worker with xuexi support."""
import json, re

# Load xuexi URLs (optional — may not exist in YSP-only workflow)
import os
xuexi_urls = {}
if os.path.exists('./work/xuexi_m3u8_authed.json'):
    with open('./work/xuexi_m3u8_authed.json', 'r') as f:
        xuexi_urls = json.load(f)
    print(f'Loaded xuexi: {len(xuexi_urls)} channels')
else:
    print('WARNING: xuexi_m3u8_authed.json not found, building without xuexi')

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

# Read the v2.7 blind worker (current base)
with open('./work/worker_v26_blind.js', 'r') as f:
    code = f.read()

# Step 1: Insert XUEXI_CATALOG after YSP_CACHE
xuexi_const = f"\n\n// XUEXI CATALOG\nconst XUEXI_CATALOG = JSON.parse('{xuexi_json_escaped}');\nconst XUEXI_CACHE = new Map();\nconst XUEXI_CACHE_TTL = 30 * 60 * 1000; // 30 min\n"
# Find the end of YSP_CACHE_TTL line
ysp_ttl_end = code.find('const YSP_CACHE_TTL = 3 * 60 * 60 * 1000;')
if ysp_ttl_end >= 0:
    ysp_ttl_line_end = code.index('\n', ysp_ttl_end) + 1
    code = code[:ysp_ttl_line_end] + xuexi_const + code[ysp_ttl_line_end:]
    print(f'1. Inserted XUEXI_CATALOG ({len(xuexi_catalog)} channels)')
else:
    print('ERROR: YSP_CACHE_TTL not found')
    exit(1)

# Step 2: Add xuexi handlers before MAIN ROUTER
router_marker = '// =================== MAIN ROUTER ==================='
xuexi_handlers = """
// =================== XUEXI HANDLERS ===================

async function handleXuexiM3u8(xuexiKey, request) {
  const ch = XUEXI_CATALOG[xuexiKey];
  if (!ch) return textResponse('Not found: ' + xuexiKey, 404);

  // Check cache
  const cached = XUEXI_CACHE.get(xuexiKey);
  if (cached && Date.now() - cached.ts < XUEXI_CACHE_TTL) {
    // Try cached URL
    try {
      const testResp = await fetch(cached.url, { method: 'HEAD', headers: { 'User-Agent': 'Mozilla/5.0' } });
      if (testResp.ok || testResp.status === 405) {
        const m3u8Url = cached.url;
        const resp = await fetch(m3u8Url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        if (resp.ok) {
          const body = await resp.text();
          return rewriteXuexiM3u8(body, ch, request);
        }
      }
    } catch (e) {}
  }

  // Use stored URL
  let m3u8Url = ch.fullUrl;
  let resp;
  try {
    resp = await fetch(m3u8Url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  } catch (e) {
    return textResponse('xuexi m3u8 fetch error: ' + e.message, 502);
  }

  if (resp.status === 403) {
    XUEXI_CACHE.delete(xuexiKey);
    triggerRefresh();
    return textResponse('xuexi m3u8 expired (403). Refresh triggered.', 502);
  }

  if (!resp.ok) {
    return textResponse('xuexi m3u8 failed: ' + resp.status, 502);
  }

  // Cache the URL
  XUEXI_CACHE.set(xuexiKey, { url: m3u8Url, ts: Date.now() });

  const body = await resp.text();
  return rewriteXuexiM3u8(body, ch, request);
}

function rewriteXuexiM3u8(m3u8body, ch, request) {
  const myOrigin = new URL(request.url).origin;
  const segBase = myOrigin + '/xseg/' + ch.host + ch.path.replace(/[^\\/]*$/, '') + '/';

  // Rewrite segment URLs (relative paths like bjtv_merge_qhd/123.ts?auth_key=...)
  const rewritten = m3u8body.split('\\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    // Relative path — prepend our proxy
    return myOrigin + '/xseg/' + encodeURIComponent(ch.host + ch.path.replace(/[^\\/]*$/, '')) + '/' + encodeURIComponent(trimmed);
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

async function handleXseg(encodedPath, filename, request) {
  // Decode the path
  let basePath;
  try {
    basePath = decodeURIComponent(encodedPath);
  } catch (e) {
    return textResponse('Invalid path encoding', 400);
  }

  // The filename might contain query params (auth_key)
  const segUrl = 'https://' + basePath + filename;

  // Try Cloudflare cache
  const cacheUrl = new URL('https://xseg-cache.iptv345.local/' + encodedPath + '/' + filename.slice(0, 50));
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
print('2. Inserted xuexi handlers')

# Step 3: Add xuexi routes
# Find the YSP routes and add xuexi routes after them
ysp_route_end = """    // /<tid><id>.m3u8  (e.g. /gt5.m3u8)"""
xuexi_routes = """    // /xuexi_<id>.m3u8  (e.g. /xuexi_b2e730bc.m3u8)
    const xuexiMatch = path.match(/^\\/(xuexi_[a-f0-9]+)\\.m3u8$/);
    if (xuexiMatch) {
      return handleXuexiM3u8(xuexiMatch[1], request);
    }

    // /xseg/<encoded_base_path>/<filename>  (xuexi segment proxy)
    const xsegMatch = path.match(/^\\/xseg\\/([^/]+)\\/(.+)$/);
    if (xsegMatch) {
      return handleXseg(xsegMatch[1], xsegMatch[2], request);
    }

"""
code = code.replace(ysp_route_end, xuexi_routes + ysp_route_end)
print('3. Inserted xuexi routes')

# Step 4: Update handleHome to add xuexi health check
# Find the ysp health check section and add xuexi after it
old_status = """  statusLine += okYsp ? 'ysp ok' : 'ysp error'; if (!okYsp) allOk = false;"""
new_status = """  statusLine += okYsp ? 'ysp ok' : 'ysp error'; if (!okYsp) allOk = false;
  statusLine += '; ';
  // xuexi health check
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
print('4. Updated handleHome with xuexi health check')

with open('./work/worker_v210_blind.js', 'w') as f:
    f.write(code)
print(f'\nv2.10 blind: {len(code)} bytes, xuexi: {len(xuexi_catalog)} channels')
