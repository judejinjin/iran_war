# API Registration Guide

Checklist of all API keys needed for the Oil Super Spike Analyzer.
Your `.env` already has: `CLAUDE_KEY`, `OPENAI_KEY`, `OPENROUTER_KEY`, `GEMINI_KEY`, `GROK_KEY`.

---

## Status Summary

| # | Service | Required? | Cost | You Have It? |
|---|---------|-----------|------|--------------|
| 1 | EIA API | **Required** | Free | No — register below |
| 2 | FRED API | **Required** | Free | No — register below |
| 3 | IB TWS API | **Required** (no key) | Free | Installed — enable API |
| 4 | Anthropic (Claude) | **Required** | Pay-per-token | Yes (`CLAUDE_KEY`) |
| 5 | NewsAPI.org | Optional fallback | Free tier (100 req/day) | No |
| 6 | Bing News (Azure) | Optional fallback | Free tier (1,000/mo) | No |
| 7 | Event Registry | Optional fallback | Free tier (2,000 articles/mo) | No |
| 8 | ACLED | Optional | Free for research | No |

**Minimum to get started**: Steps 1, 2, and 3 only. Everything else is either already in your `.env` or optional.

---

## Step 1: EIA API Key (Required, Free)

The U.S. Energy Information Administration provides oil production, inventory, and supply data.

1. Go to: **https://www.eia.gov/opendata/register.php**
2. Fill in:
   - **Name**: your name
   - **Email**: your email
   - **Affiliation**: can put "Individual" or "Personal research"
3. Click **Register**
4. Check your email — the API key arrives instantly
5. Copy the key and add to `.env`:
   ```
   EIA_API_KEY=your_key_here
   ```

**Verify it works** (in browser or curl):
```
https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=YOUR_KEY&frequency=daily&data[0]=value&facets[series][]=RWTC&length=5
```
You should see JSON with recent WTI spot prices.

---

## Step 2: FRED API Key (Required, Free)

The Federal Reserve Economic Data service provides historical WTI and Brent daily spot prices.

1. Go to: **https://fred.stlouisfed.org/docs/api/api_key.html**
2. Click **"Request API Key"** (you'll be redirected to a FRED account page)
3. If you don't have a FRED account:
   - Click **"Create New Account"**
   - Enter email, create password
   - Verify email
4. Once logged in, go back to the API key page and click **"Request API Key"**
5. Fill in:
   - **Description**: "Oil market research" (anything works)
6. The key appears immediately on screen
7. Copy and add to `.env`:
   ```
   FRED_API_KEY=your_key_here
   ```

**Verify it works** (in browser):
```
https://api.stlouisfed.org/fred/series/observations?series_id=DCOILWTICO&api_key=YOUR_KEY&file_type=json&limit=5&sort_order=desc
```
You should see JSON with recent WTI spot price observations.

---

## Step 3: Interactive Brokers TWS — Enable API (Required, No Key)

TWS Desktop is already installed. You just need to enable the socket API so our Python code can connect.

1. **Open TWS Desktop** and log in
2. Go to **File → Global Configuration** (or Edit → Global Configuration on some versions)
3. In the left tree, navigate to: **API → Settings**
4. Check these boxes:
   - [x] **Enable ActiveX and Socket Clients**
   - [x] **Allow connections from localhost only** (security)
5. Set **Socket port**:
   - `7497` for paper trading
   - `7496` for live trading
6. Set **Master API client ID**: `1` (or leave default)
7. Under **Precautions**, optionally uncheck "Read-Only API" if you want to place orders later
8. Click **Apply** then **OK**
9. **Restart TWS** if prompted

**Verify it works** — Quick Python test (after project setup):
```python
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # 7497=paper, 7496=live
print(ib.isConnected())  # Should print True
ib.disconnect()
```

**Note**: TWS must be running whenever the project's scheduler collects market data. TWS auto-logs out daily — consider enabling **Auto-restart** in TWS settings (File → Global Configuration → Lock and Exit → Auto-restart).

---

## Step 4: Anthropic Claude API — Already Done ✓

Your `.env` already has `CLAUDE_KEY`. Just verify it's active:

**Verify** (in PowerShell):
```powershell
$headers = @{ "x-api-key" = "YOUR_CLAUDE_KEY"; "anthropic-version" = "2023-06-01"; "content-type" = "application/json" }
$body = '{"model":"claude-sonnet-4-20250514","max_tokens":50,"messages":[{"role":"user","content":"Say hello"}]}'
Invoke-RestMethod -Uri "https://api.anthropic.com/v1/messages" -Method Post -Headers $headers -Body $body
```

If you get a response with "hello", it's working.

**Check your usage/billing**: https://console.anthropic.com/settings/billing

---

## Step 5: NewsAPI.org (Optional Fallback, Free Tier)

Structured news search. Free tier: 100 requests/day, headlines from last 24h only.

1. Go to: **https://newsapi.org/register**
2. Enter:
   - **Name**: your name
   - **Email**: your email
   - **Password**: create one
3. Click **Submit**
4. Your API key appears immediately on the dashboard
5. Add to `.env`:
   ```
   NEWSAPI_KEY=your_key_here
   ```

**Verify** (in browser):
```
https://newsapi.org/v2/everything?q=iran+oil&apiKey=YOUR_KEY&pageSize=3
```

**Free tier limitations**: only returns articles from the past 24 hours; search within the past month requires paid plan ($449/mo — not recommended).

---

## Step 6: Bing News Search API (Optional Fallback, Free Tier)

Microsoft Cognitive Services news search. Free tier: 1,000 calls/month.

1. Go to: **https://portal.azure.com/** and sign in (or create a free Azure account)
2. If creating a new Azure account:
   - You'll need a Microsoft account (Outlook, Hotmail, or create one)
   - Azure free account requires a credit card for verification (won't be charged)
   - You get $200 free credit for 30 days
3. Once in the Azure Portal:
   - Click **"Create a resource"** (top-left + icon)
   - Search for **"Bing Search v7"** (or "Bing Search")
   - Click **Create**
   - **Resource group**: create new or use existing
   - **Name**: anything (e.g., "oil-news-search")
   - **Pricing tier**: select **F1 (Free — 1,000 calls/month)**
   - Click **Review + Create**, then **Create**
4. Once deployed, go to the resource
5. Click **"Keys and Endpoint"** in the left menu
6. Copy **Key 1**
7. Add to `.env`:
   ```
   BING_NEWS_KEY=your_key_here
   ```

**Verify** (PowerShell):
```powershell
$headers = @{ "Ocp-Apim-Subscription-Key" = "YOUR_KEY" }
Invoke-RestMethod -Uri "https://api.bing.microsoft.com/v7.0/news/search?q=iran+oil+war&count=3" -Headers $headers
```

---

## Step 7: Event Registry (Optional Fallback, Free Tier)

NLP-enriched, entity-tagged news articles. Free tier: 2,000 articles/month.

1. Go to: **https://eventregistry.org/**
2. Click **"Sign Up"** (top right) or go to **https://eventregistry.org/register**
3. Enter email and password, click Register
4. Verify your email
5. Log in, then go to **https://eventregistry.org/me/account** (or click your profile → Account)
6. Your **API Key** is shown on the account page
7. Add to `.env`:
   ```
   EVENT_REGISTRY_KEY=your_key_here
   ```

**Verify** (in browser):
```
https://eventregistry.org/api/v1/article/getArticles?query=%7B%22keyword%22%3A%22Iran%20oil%22%7D&resultType=articles&articlesSortBy=date&articlesCount=3&apiKey=YOUR_KEY
```

---

## Step 8: ACLED (Optional, Free for Research)

Armed Conflict Location & Event Data — geolocated conflict events with fatality counts. Used for military losses module.

1. Go to: **https://acleddata.com/register/**
2. Fill in the registration form:
   - **Type of Organization**: select "Individual / Independent Researcher"
   - **Organization / Affiliation**: "Independent"
   - **Intended Use**: "Conflict analysis for investment research"
   - **Name, email, etc.**
3. Check the terms-of-use box
4. Click **Register**
5. You'll receive an email with your **API key** and **email** (both needed for requests)
6. Add to `.env`:
   ```
   ACLED_API_KEY=your_key_here
   ACLED_EMAIL=your_email_here
   ```

**Verify** (in browser):
```
https://api.acleddata.com/acled/read?key=YOUR_KEY&email=YOUR_EMAIL&country=Iran&limit=5
```
You should see JSON with geolocated conflict events in Iran.

**Note**: ACLED review may take 1–2 business days for approval. If you need to start immediately, the project works without it — military data will come from news articles + AI extraction instead.

---

## Final .env File

After completing all steps, your `.env` should look like:

```env
# Already present
GEMINI_KEY=...
OPENAI_KEY=...
CLAUDE_KEY=...
OPENROUTER_KEY=...
GROK_KEY=...

# NEW — Required (free)
EIA_API_KEY=your_eia_key_here
FRED_API_KEY=your_fred_key_here

# NEW — Optional fallbacks (free tiers)
NEWSAPI_KEY=your_newsapi_key_here
BING_NEWS_KEY=your_azure_key_here
EVENT_REGISTRY_KEY=your_er_key_here
ACLED_API_KEY=your_acled_key_here
ACLED_EMAIL=your_acled_email_here
```

---

## Priority Order

If you're short on time, register in this order:

1. **EIA** — 2 minutes, instant key ← do this first
2. **FRED** — 3 minutes, instant key ← do this second
3. **IB TWS** — 2 minutes, just toggle settings ← do this third
4. *(Everything else is optional — the project works without steps 5–8)*
