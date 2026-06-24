#!/usr/bin/env python3
"""Fetch all xuexi.cn channel m3u8 URLs by fetching each channel's page data JSON."""
import json, urllib.request, ssl, re, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return json.loads(r.read().decode('utf8'))
    except Exception as e:
        print(f'  ERROR: {e}')
        return None

def find_video_link(data):
    """Recursively find videoLink in JSON data."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k == 'videoLink' and isinstance(v, str) and v.startswith('http'):
                return v
            result = find_video_link(v)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_video_link(item)
            if result:
                return result
    return None

def find_tab_title(data):
    """Find tabTitle for naming."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k == 'tabTitle' and isinstance(v, str):
                return v
            if k == 'text' and isinstance(v, str):
                return v
            result = find_tab_title(v)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_tab_title(item)
            if result:
                return result
    return None

# Step 1: Fetch the channel list (local stations)
print("=== Fetching local station list ===")
local_url = "https://www.xuexi.cn/lgdata/4e7glnu0jkjf.json?_st=29704706"
local_data = fetch_json(local_url)
if not local_data:
    print("Failed to fetch local station list")
    exit(1)

# Extract channel IDs
channels = []
for ch in local_data:
    title = ch.get('title', '')
    url = ch.get('url', '')
    if 'xxqg.html?id=' in url:
        ch_id = url.split('id=')[1].split('&')[0]
        channels.append({'name': title, 'id': ch_id, 'url': url})
    elif url.startswith('http'):
        # External link (三沙卫视, etc.) — skip
        channels.append({'name': title, 'id': None, 'url': url, 'external': True})

print(f"Found {len(channels)} local channels")
for ch in channels:
    print(f"  {ch['name']}: id={ch.get('id', 'N/A')} url={ch['url'][:80]}")

# Step 2: Also check for CETV and CCTV channels
# The CCTV channels are at: 4hhlhqihqqjg.json (external links to tv.cctv.com)
# But xuexi also has CCTV streams — let me check the main page data
print("\n=== Fetching CCTV channel list ===")
cctv_url = "https://www.xuexi.cn/lgdata/4hhlhqihqqjg.json?_st=29704706"
cctv_data = fetch_json(cctv_url)
if cctv_data:
    for ch in cctv_data:
        title = ch.get('title', '')
        url = ch.get('url', '')
        if 'xxqg.html?id=' in url:
            ch_id = url.split('id=')[1].split('&')[0]
            channels.append({'name': title, 'id': ch_id, 'url': url})
            print(f"  {title}: id={ch_id}")

# Step 3: Fetch each channel's m3u8 URL
print(f"\n=== Fetching m3u8 URLs for {len([c for c in channels if c.get('id')])} channels ===")
results = {}
for ch in channels:
    if not ch.get('id'):
        print(f"  SKIP {ch['name']}: no ID (external link)")
        continue
    
    ch_url = f"https://www.xuexi.cn/lgdata/{ch['id']}.json"
    print(f"  {ch['name']} ({ch['id']})...", end='', flush=True)
    data = fetch_json(ch_url)
    if data:
        video_link = find_video_link(data)
        if video_link:
            print(f" ✓ {video_link[:80]}")
            # Generate the key name: xuexi_<channel_name_in_pinyin_or_short>
            # Use the channel ID as the key for simplicity
            key = 'xuexi_' + ch['id'][:8]
            results[key] = {
                'name': ch['name'],
                'id': ch['id'],
                'fullUrl': video_link,
            }
        else:
            print(f" ✗ no videoLink found")
    else:
        print(f" ✗ fetch failed")
    time.sleep(0.3)

# Step 4: Test if the m3u8 URLs work without auth_key
print(f"\n=== Testing m3u8 URLs ({len(results)} channels) ===")
for key, data in results.items():
    url = data['fullUrl']
    # Check if URL has auth_key — if so, it needs refreshing
    has_auth = 'auth_key' in url
    print(f"  {data['name']}: {url[:100]}")
    print(f"    has auth_key: {has_auth}")
    
    # Try fetching the m3u8
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            body = r.read().decode('utf8')[:200]
            print(f"    status: {r.status}, body: {body[:100]}")
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}")
    except Exception as e:
        print(f"    ERROR: {e}")

# Save results
with open('./work/xuexi_m3u8_urls.json', 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nSaved {len(results)} channels to xuexi_m3u8_urls.json")

# Generate xuexi-iptv.txt
lines = []
for key, data in results.items():
    lines.append(f"{data['name']},https://iptv345.lishuhang.workers.dev/{key}.m3u8")
with open('./work/xuexi-iptv.txt', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print(f"Saved xuexi-iptv.txt ({len(lines)} entries)")
