# 345 Worker Auto-Refresh

This repo automatically refreshes YSP and xuexi m3u8 URLs and deploys to Cloudflare Workers.

## How it works

1. GitHub Actions runs every 20 minutes
2. Uses Playwright to open yangshipin.cn and xuexi.cn
3. Captures fresh m3u8 URLs with auth_key
4. Builds the Worker JS with embedded URLs
5. Deploys to Cloudflare Workers via API

## Secrets required

- `CF_API_TOKEN` - Cloudflare API token
- `ACCOUNT_ID` - Cloudflare account ID

## Manual trigger

Go to Actions tab → "Refresh URLs and Deploy" → "Run workflow"
