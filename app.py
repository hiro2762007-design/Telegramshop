import os
import mimetypes
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
# Backward compatibility for existing projects; Supabase is deprecating legacy service_role keys by end of 2026.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_API_KEY = SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "product-images")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()

def config_ready():
    return bool(SUPABASE_URL and SUPABASE_API_KEY)

def supabase_headers(extra=None):
    # New sb_secret_* keys are opaque API keys: send them only via `apikey`.
    # Legacy service_role JWTs also work with the Authorization Bearer header.
    headers = {"apikey": SUPABASE_API_KEY}
    if not SUPABASE_SECRET_KEY and SUPABASE_SERVICE_ROLE_KEY:
        headers["Authorization"] = f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
    if extra:
        headers.update(extra)
    return headers

def upload_telegram_photo(file_id, message_id):
    """Download the largest Telegram photo and upload it to public Supabase Storage."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    meta = requests.get(f"{api}/getFile", params={"file_id": file_id}, timeout=20)
    meta.raise_for_status()
    payload = meta.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram getFile failed")
    file_path = payload["result"]["file_path"]
    image_response = requests.get(
        f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
        timeout=30,
    )
    image_response.raise_for_status()
    content_type = image_response.headers.get("Content-Type") or mimetypes.guess_type(file_path)[0] or "image/jpeg"
    extension = os.path.splitext(file_path)[1] or ".jpg"
    object_path = f"telegram/{message_id}{extension}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{object_path}"
    headers = supabase_headers({
        "Content-Type": content_type,
        "x-upsert": "true",
    })
    uploaded = requests.post(upload_url, headers=headers, data=image_response.content, timeout=30)
    uploaded.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{object_path}"

def save_product(post):
    chat = post.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    message_id = post.get("message_id")
    caption = (post.get("caption") or post.get("text") or "").strip()
    lines = [line.strip() for line in caption.splitlines() if line.strip()]
    name = lines[0] if lines else "အမည်မဖော်ပြထားသော ပစ္စည်း"
    image_url = None

    photos = post.get("photo") or []
    if photos and TELEGRAM_BOT_TOKEN:
        # Telegram photo sizes are ordered from small to large.
        image_url = upload_telegram_photo(photos[-1]["file_id"], message_id)

    product = {
        "telegram_chat_id": chat_id,
        "telegram_message_id": message_id,
        "name": name,
        "description": caption,
        "image_url": image_url,
        "telegram_date": post.get("date"),
    }
    url = f"{SUPABASE_URL}/rest/v1/products?on_conflict=telegram_chat_id,telegram_message_id"
    headers = supabase_headers({
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    })
    response = requests.post(url, headers=headers, json=product, timeout=20)
    response.raise_for_status()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "supabase_configured": config_ready(),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
    })

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    if not config_ready():
        return jsonify({"ok": False, "error": "Supabase environment variables are missing"}), 503

    if TELEGRAM_WEBHOOK_SECRET:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if supplied != TELEGRAM_WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

    update = request.get_json(silent=True) or {}
    post = update.get("channel_post") or update.get("edited_channel_post")
    if not post:
        return jsonify({"ok": True, "ignored": True})

    chat_id = str((post.get("chat") or {}).get("id", ""))
    if TELEGRAM_CHANNEL_ID and chat_id != TELEGRAM_CHANNEL_ID:
        return jsonify({"ok": True, "ignored": True, "reason": "channel_not_allowed"})

    try:
        save_product(post)
        return jsonify({"ok": True})
    except requests.RequestException as exc:
        app.logger.exception("External API request failed")
        return jsonify({"ok": False, "error": "Could not save Telegram post"}), 502
    except Exception:
        app.logger.exception("Webhook processing failed")
        return jsonify({"ok": False, "error": "Webhook processing failed"}), 500

@app.route("/api/products", methods=["GET"])
def get_products():
    if not config_ready():
        return jsonify({"error": "Supabase is not configured"}), 503
    url = f"{SUPABASE_URL}/rest/v1/products?select=id,name,description,image_url,created_at&order=created_at.desc"
    response = requests.get(url, headers=supabase_headers(), timeout=20)
    response.raise_for_status()
    return jsonify(response.json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
