// =================== YSP HANDLERS ===================

async function getYspM3u8Url(yspKey) {
  const cached = YSP_CACHE.get(yspKey);
  if (cached && Date.now() - cached.ts < YSP_CACHE_TTL) {
    return cached.url;
  }
  const ch = YSP_CATALOG[yspKey];
  if (!ch) return null;
  YSP_CACHE.set(yspKey, { url: ch.fullUrl, ts: Date.now() });
  return ch.fullUrl;
}

async function handleYspM3u8(yspKey, request) {
  const ch = YSP_CATALOG[yspKey];
  if (!ch) return textResponse('Not found: ' + yspKey, 404);

  const m3u8Url = await getYspM3u8Url(yspKey);
  if (!m3u8Url) return textResponse('YSP URL not available', 502);

  let resp;
  try {
    resp = await fetch(m3u8Url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' },
    });
  } catch (e) {
    return textResponse('YSP m3u8 fetch error: ' + e.message, 502);
  }

  if (resp.status === 403) {
    YSP_CACHE.delete(yspKey);
    return textResponse('YSP m3u8 expired (403). Please refresh YSP URLs.', 502);
  }

  if (!resp.ok) {
    return textResponse('YSP m3u8 failed: ' + resp.status, 502);
  }

  const m3u8body = await resp.text();
  const myOrigin = new URL(request.url).origin;
  const segBase = myOrigin + '/yseg/' + yspKey + '/';

  // Rewrite segment URLs
  const mediaPlaylist = m3u8body.split('\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      try { const u = new URL(trimmed); return segBase + u.pathname.substring(u.pathname.lastIndexOf('/') + 1); }
      catch (e) { return line; }
    }
    return segBase + trimmed;
  }).join('\n');

  // Two-level playlist: master (with CODECS) -> media (segment list)
  // This prevents hls.js from auto-detecting an incorrect codec string.
  const url = new URL(request.url);
  if (url.searchParams.get('media') === '1') {
    // Media playlist request (from the master playlist)
    return new Response(mediaPlaylist, {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.apple.mpegurl',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'CDN-Cache-Control': 'no-store',
      },
    });
  }

  // Master playlist with explicit CODECS
  const masterPlaylist = '#EXTM3U\n' +
    '#EXT-X-VERSION:3\n' +
    '#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,CODECS="avc1.640029,mp4a.40.2"\n' +
    myOrigin + '/' + yspKey + '.m3u8?media=1\n';

  return new Response(masterPlaylist, {
    status: 200,
    headers: {
      'Content-Type': 'application/vnd.apple.mpegurl',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'CDN-Cache-Control': 'no-store',
    },
  });
}

async function handleYseg(yspKey, filename, request) {
  const ch = YSP_CATALOG[yspKey];
  if (!ch) return textResponse('Not found: ' + yspKey, 404);

  const qIdx = filename.indexOf('?');
  const cleanFilename = qIdx >= 0 ? filename.substring(0, qIdx) : filename;
  const basePath = ch.path.substring(0, ch.path.lastIndexOf('/') + 1);
  const segUrl = 'https://' + ch.host + basePath + cleanFilename;

  const cacheUrl = new URL('https://yseg-cache.iptv345.local/' + yspKey + '/' + cleanFilename);
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
    upstream = await fetch(segUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' },
    });
  } catch (e) { return textResponse('YSP segment error: ' + e.message, 502); }

  if (!upstream.ok) return textResponse('YSP segment failed: ' + upstream.status, 502);

  const body = await upstream.arrayBuffer();
  const resp = new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'video/mp2t', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=600', 'X-Cache': 'MISS' },
  });
  try { cache.put(cacheKey, resp.clone()).catch(() => {}); } catch (e) {}
  return resp;
}

