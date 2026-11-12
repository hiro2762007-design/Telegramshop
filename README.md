# Telegram Shop + Supabase

Flask website that receives Telegram channel posts through a webhook, stores product data in Supabase Postgres, uploads Telegram photos to Supabase Storage, and displays products on the website.

## 1. Create Supabase resources

1. Create a project at https://supabase.com.
2. Open **SQL Editor**, paste `schema.sql`, and run it.
3. Open **Settings > API Keys** and copy the Project URL and create/copy a new `sb_secret_...` secret key for server-side use.
4. Keep the secret key private. It belongs only in Render's server environment (or your local `.env` file), never in browser code or Git.
5. The app also supports the legacy `service_role` JWT as a fallback, but Supabase is deprecating legacy `service_role` keys by the end of 2026; use the new secret key for a fresh setup.

## 2. Configure the app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`

Optional: set `TELEGRAM_CHANNEL_ID` to your channel's numeric ID to accept posts only from that channel.

## 3. Deploy the website on Render

This project includes `render.yaml` for a Render Python Web Service.

1. Create a private GitHub repository and upload the contents of this project (the files inside this folder, not the ZIP itself). Keep `.env` out of Git; `.gitignore` already excludes it.
2. Open https://dashboard.render.com and choose **New > Blueprint**.
3. Connect GitHub and select the repository. Render reads `render.yaml` and prepares a Python web service.
4. When prompted, enter `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_WEBHOOK_SECRET` in Render's secret fields. Never commit these values or put them in `index.html`.
5. Approve the Blueprint deploy. The service settings use `pip install -r requirements.txt` and `gunicorn app:app`; the health check is `/health`.
6. After deployment, copy the public `https://...onrender.com` URL and open `https://YOUR_PUBLIC_DOMAIN/health`. It should report `ok: true`, `supabase_configured: true`, and `telegram_configured: true`. This health endpoint checks that environment values are present; it does not prove that Supabase credentials work. Then open `https://YOUR_PUBLIC_DOMAIN/api/products`: it should return `[]` for an empty table or a JSON product list. An API error means the Supabase connection/schema still needs troubleshooting.

Render's free web services can spin down after 15 minutes without traffic, so the first request after inactivity may take longer. See Render's current plan details before using it for a production shop.

## 4. Add the bot to your channel

1. Create a bot with Telegram **@BotFather** and copy its token.
2. Add the bot to your Telegram channel as an **administrator**. It needs permission to post/read channel updates.
3. Confirm the Render service is live at a public HTTPS URL. Telegram webhooks cannot call `localhost`.
4. On your own Mac/Linux terminal, set the webhook without typing secrets directly into the command history:

```bash
read -s -p "Telegram bot token: " BOT_TOKEN; echo
read -s -p "Webhook secret: " WEBHOOK_SECRET; echo
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://YOUR_PUBLIC_DOMAIN/webhook" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["channel_post","edited_channel_post"]'
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
unset BOT_TOKEN WEBHOOK_SECRET
```

Replace `YOUR_PUBLIC_DOMAIN` with the actual Render hostname. Use the same webhook secret value that you entered in Render's environment settings. In the `getWebhookInfo` response, confirm that `url` is your public `/webhook` URL and that `last_error_message` is absent or empty. Do not share the token or the returned webhook URL if it contains sensitive information.

Optional: add `TELEGRAM_CHANNEL_ID` in the Render service's **Environment** settings to restrict product imports to one channel.

## 5. Run locally (website/API testing only)

```bash
python app.py
```

Open http://127.0.0.1:5000. Localhost is not publicly reachable by Telegram, so channel webhook testing requires HTTPS deployment or a secure HTTPS tunnel.

## 6. Post format

Post a photo with a caption in your channel. The first non-empty caption line becomes the product name; the full caption is saved as the description. Example:

```text
Men T-Shirt
Price - 25,000 MMK
Size - M / L / XL
```

Photo uploads are stored in the public `product-images` bucket. Text-only posts are saved without an image.

## Important security notes

- Never put the Supabase secret key (or legacy `service_role` key) or Telegram bot token in `index.html` or any public frontend JavaScript.
- Keep `.env` private and do not upload it to GitHub.
- Use a long random `TELEGRAM_WEBHOOK_SECRET`.
- Configure `TELEGRAM_CHANNEL_ID` to restrict which channel can create products.
- The webhook uses Telegram message identity to avoid duplicate product rows on retry.
