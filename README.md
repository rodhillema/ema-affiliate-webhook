# ĒMA Affiliate Interest Form — Jotform → Notion Webhook

Automatically populates three Notion databases whenever the affiliate
interest form is submitted on Jotform.

**Flow:**
1. Jotform form submitted
2. Webhook hits `/webhook` on this server
3. Find or create **Organization** record
4. Find or create **Contact** record (linked to org)
5. Create **Meeting** page (linked to org + contact, with all Q&A in body)

---

## Setup

### 1. Get your Notion Integration Token

1. Go to https://www.notion.so/my-integrations
2. Click **+ New integration**
3. Name it "EMA Affiliate Webhook", select your workspace
4. Copy the **Internal Integration Token** (starts with `secret_`)
5. **Important:** Open each of your three Notion databases, click the
   `...` menu → **Connections** → add your new integration

### 2. Get the Notion Database IDs

These are already pre-filled in `.env.example` based on your URLs:
- Organizations: `1cbecd674a69812fa5d2f4ea66306912`
- Contacts:      `1cbecd674a6981acb3a7ea644e66acdf`
- Meetings/Docs: `f57175f8a2e6460880acffb1419e968b`

### 3. Deploy to Railway

1. Push this repo to GitHub
2. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**
3. Select this repo
4. Go to your service → **Variables** tab, add:
   - `NOTION_TOKEN` = your integration token
   - `NOTION_ORG_DB` = `1cbecd674a69812fa5d2f4ea66306912`
   - `NOTION_CONTACT_DB` = `1cbecd674a6981acb3a7ea644e66acdf`
   - `NOTION_MEETING_DB` = `f57175f8a2e6460880acffb1419e968b`
5. Railway auto-deploys. Copy your public URL (e.g. `https://ema-webhook.up.railway.app`)

### 4. Connect Jotform

1. Go to your form in Jotform → **Settings** → **Integrations**
2. Search for **Webhooks**
3. Add webhook URL: `https://your-railway-url.up.railway.app/webhook`
4. Save

### 5. Verify field names (important!)

Jotform field token names vary. To confirm yours:

1. Temporarily change your webhook URL to `.../debug`
2. Submit a test form entry
3. Check Railway logs — you'll see all the raw field names
4. Compare to the mappings in `parse_form()` in `app.py`
5. Adjust any that don't match, then switch back to `/webhook`

---

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (Railway uses this) |
| `/webhook` | POST | Main Jotform webhook receiver |
| `/debug` | POST | Dumps raw Jotform fields for debugging |

---

## Local development

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in your values
python app.py
```

Then test with:
```bash
curl http://localhost:5000/health
```
