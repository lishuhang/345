#!/usr/bin/env python3
"""Deploy worker to Cloudflare Workers."""
import urllib.request, ssl, os, json, sys

CF_API_TOKEN = os.environ.get('CF_API_TOKEN', '')
ACCOUNT_ID = os.environ.get('ACCOUNT_ID', '')
WORKER_NAME = 'iptv345'
WORKER_FILE = '/workspace/work/worker.js'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def cf_request(method, path, body=None, content_type='application/json'):
    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {'Authorization': f'Bearer {CF_API_TOKEN}', 'Content-Type': content_type}
    data = body.encode('utf8') if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.status, r.read().decode('utf8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf8')

# Read worker
with open(WORKER_FILE, 'r', encoding='utf8') as f:
    worker_code = f.read()

print(f'Worker code: {len(worker_code)} bytes')

# Upload
boundary = '----cf-deploy-' + os.urandom(8).hex()
metadata = json.dumps({"main_module": "worker.js", "compatibility_date": "2024-09-23"})
body_parts = []
body_parts.append(f'--{boundary}\r\n'.encode())
body_parts.append(b'Content-Disposition: form-data; name="metadata"\r\n')
body_parts.append(b'Content-Type: application/json\r\n\r\n')
body_parts.append(metadata.encode() + b'\r\n')
body_parts.append(f'--{boundary}\r\n'.encode())
body_parts.append(b'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n')
body_parts.append(b'Content-Type: application/javascript+module\r\n\r\n')
body_parts.append(worker_code.encode('utf8') + b'\r\n')
body_parts.append(f'--{boundary}--\r\n'.encode())
body = b''.join(body_parts)

status, resp = cf_request('PUT', f'/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}',
                          body=body, content_type=f'multipart/form-data; boundary={boundary}')
print(f'Upload: {status}')
if status != 200:
    print(f'Failed: {resp[:500]}')
    sys.exit(1)

# Enable subdomain
cf_request('POST', f'/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}/subdomain',
           body=json.dumps({"enabled": True}))
print('Deployed successfully')
