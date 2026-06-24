#!/usr/bin/env python3
"""Apply the xuexi segment proxy fix to the built worker."""
with open('/workspace/work/worker_v210_blind.js', 'r') as f:
    code = f.read()

# Fix 1: rewriteXuexiM3u8
old1 = '''function rewriteXuexiM3u8(m3u8body, ch, request) {
  const myOrigin = new URL(request.url).origin;
  const segBase = myOrigin + '/xseg/' + ch.host + ch.path.replace(/[^\\/]*$/, '') + '/';

  // Rewrite segment URLs (relative paths like bjtv_merge_qhd/123.ts?auth_key=...)
  const rewritten = m3u8body.split('\\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    // Relative path — prepend our proxy
    return myOrigin + '/xseg/' + encodeURIComponent(ch.host + ch.path.replace(/[^\\/]*$/, '')) + '/' + encodeURIComponent(trimmed);
  }).join('\\n');'''
new1 = '''function rewriteXuexiM3u8(m3u8body, ch, request) {
  const myOrigin = new URL(request.url).origin;
  const basePath = ch.path.replace(/[^\\/]*$/, '');
  const rewritten = m3u8body.split('\\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    return myOrigin + '/xseg2/' + ch.host + basePath + trimmed;
  }).join('\\n');'''
code = code.replace(old1, new1)

# Fix 2: handleXseg -> handleXseg2
old2 = '''async function handleXseg(encodedPath, filename, request) {
  // Decode the path
  let basePath;
  try {
    basePath = decodeURIComponent(encodedPath);
  } catch (e) {
    return textResponse('Invalid path encoding', 400);
  }

  // The filename might contain query params (auth_key)
  const segUrl = 'https://' + basePath + filename;'''
new2 = '''async function handleXseg2(fullPath, request) {
  const slashIdx = fullPath.indexOf('/');
  if (slashIdx < 0) return textResponse('Invalid xseg2 path', 400);
  const host = fullPath.substring(0, slashIdx);
  const pathAndQuery = fullPath.substring(slashIdx);
  const segUrl = 'https://' + host + pathAndQuery;'''
code = code.replace(old2, new2)

# Fix 3: cache URL
code = code.replace(
    "const cacheUrl = new URL('https://xseg-cache.iptv345.local/' + encodedPath + '/' + filename.slice(0, 50));",
    "const cacheUrl = new URL('https://xseg-cache.iptv345.local/' + fullPath.slice(0, 100));"
)

# Fix 4: routes
old4 = '''    // /xseg/<encoded_base_path>/<filename>  (xuexi segment proxy)
    const xsegMatch = path.match(/^\\/xseg\\/([^/]+)\\/(.+)$/);
    if (xsegMatch) {
      return handleXseg(xsegMatch[1], xsegMatch[2], request);
    }'''
new4 = '''    // /xseg2/<host>/<path>  (xuexi segment proxy)
    const xseg2Match = path.match(/^\\/xseg2\\/(.+)$/);
    if (xseg2Match) {
      return handleXseg2(xseg2Match[1] + url.search, request);
    }'''
code = code.replace(old4, new4)

with open('/workspace/work/worker_v210_blind.js', 'w') as f:
    f.write(code)
print('Segment fix applied')
