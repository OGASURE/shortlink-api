# Workpent Shortlink API like the best#

Minimal, production-ready link shortener API built with **FastAPI + SQLite**.

> Powering SMS links, WhatsApp campaigns, ISP vouchers, email CTAs and more – designed to plug into the wider **Workpent** ecosystem.

---

## ✨ Features

- 🔗 Create short links for any valid URL
- 🧩 Optional **custom codes** (e.g. `/promo2025`)
- 📊 Click tracking:
  - total clicks
  - last clicked time
- ✅ Simple **health** endpoint for monitoring
- 📚 Auto-generated Swagger docs (`/docs`)
- 🗃️ Lightweight **SQLite** storage (single `.db` file)
- 🧱 Clean JSON API – ready for SMS, WhatsApp, email or browser integrations

---

## 🚀 Quick start (local / VPS)

> These commands assume you already cloned the repo and are inside the project folder.

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional – base public URL used in responses
export BASE_SHORT_URL="http://localhost:9500"

uvicorn main:app --host 0.0.0.0 --port 9500
