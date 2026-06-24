# Cleany – Automated Data Cleaning & Reporting Platform

Cleany is a production-ready Flask web application that lets users upload CSV/Excel
datasets and automatically cleans the data, profiles it, generates AI-powered
insights, lets users chat with their dataset in natural language, and produces
downloadable PDF/Excel/CSV reports.

## Features

- **Auth** — register, login, logout (hashed passwords, session-based)
- **Upload** — CSV / Excel validation, 50MB limit
- **Automated cleaning** — missing value treatment, duplicate removal, IQR & Z-score
  outlier detection, data type correction, text/date standardization
- **Profiling** — rows, columns, dtypes, missing %, duplicates, outliers
- **AI dataset understanding** — domain detection, numeric/categorical/date columns,
  potential target variables
- **EDA** — summary stats, correlation matrix, histograms, box plots, heatmaps
  (interactive Plotly charts in-browser, static Seaborn/Matplotlib charts in PDF)
- **AI Data Quality Score** — 0–100 score with a penalty breakdown
- **AI Insight Generator** — executive summary, key findings, business insights,
  risks, recommendations, data quality observations
- **Dataset Chat Assistant** — ask natural-language questions about your data
- **Report Generator** — downloadable PDF, Excel, and cleaned CSV
- **Dashboard** — manage all uploaded datasets in one place

### AI provider configuration

Cleany integrates with OpenAI or Google Gemini for insight generation and dataset
chat. Set `OPENAI_API_KEY` or `GEMINI_API_KEY` in your environment (see
`.env.example`). **If neither key is set, Cleany automatically falls back to a
built-in rule-based / pandas-driven engine**, so the app is fully functional out
of the box with zero external API dependency.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript, Plotly.js |
| Backend | Python, Flask |
| Data processing | Pandas, NumPy, Scikit-learn |
| Database | SQLite |
| Visualization | Plotly, Matplotlib, Seaborn |
| Reporting | ReportLab (PDF), OpenPyXL (Excel) |
| AI | OpenAI / Gemini API, LangChain-compatible design |

## Project Structure

```
/cleany
  /templates        Jinja2 HTML templates
  /static
    /css             style.css
    /js              main.js
  /uploads           Uploaded + cleaned datasets (gitignored)
  /reports           Generated PDF/Excel/CSV reports (gitignored)
  /database          schema.sql, db.py, cleany.db (gitignored)
  /utils
    cleaning.py       Cleaning pipeline
    profiling.py      Profiling, dataset understanding, quality score
    charts.py         Plotly + Matplotlib/Seaborn chart generation
    ai_engine.py       AI insights + dataset chat (LLM + heuristic fallback)
    reports.py        PDF/Excel/CSV report builders
    auth.py           Password hashing, validators, login_required
  app.py              Flask app & routes
  requirements.txt
  .env.example
  README.md
```

## Database Schema

- **users**(id, username, email, password_hash, created_at)
- **uploaded_files**(id, user_id, original_filename, stored_filename,
  cleaned_filename, file_type, rows, columns, quality_score, uploaded_at)
- **reports**(id, file_id, user_id, report_type, report_path, generated_at)
- **chat_history**(id, file_id, user_id, question, answer, created_at)

See `database/schema.sql` for full DDL.

## Local Setup

```bash
git clone <repo-url> cleany
cd cleany
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # fill in SECRET_KEY and optional AI keys
python app.py
```

App runs at `http://localhost:5000`. The SQLite database and folders are
created automatically on first run.

## API / Route Summary

| Route | Method | Description |
|---|---|---|
| `/` | GET | Landing page |
| `/register` | GET/POST | Create account |
| `/login` | GET/POST | Authenticate |
| `/logout` | GET | End session |
| `/dashboard` | GET | List user's datasets |
| `/upload` | POST | Upload a CSV/Excel file |
| `/process/<file_id>` | GET | Run cleaning/profiling/AI pipeline, show results |
| `/chat/<file_id>` | GET/POST | Dataset chat UI / ask a question (JSON) |
| `/report/<file_id>/<type>` | GET | Generate report (`pdf`, `excel`, `csv`) |
| `/reports/download/<filename>` | GET | Download a generated report |
| `/delete/<file_id>` | POST | Delete a dataset and its files |
| `/api/health` | GET | Health check (JSON) |

## Security Notes

- Passwords hashed with Werkzeug's `generate_password_hash` (PBKDF2)
- Filenames sanitized with `secure_filename` + UUID prefixing to prevent collisions/traversal
- File type and size validated server-side
- `login_required` decorator protects all dataset/report routes
- Per-user row scoping on every database query (`WHERE user_id = ?`)
- Set a strong, random `SECRET_KEY` in production (never commit `.env`)
- Use HTTPS in production (reverse proxy/load balancer termination)

## Deployment

### Render
1. Push the repo to GitHub.
2. Create a **New Web Service** on Render, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add environment variables: `SECRET_KEY`, `OPENAI_API_KEY`/`GEMINI_API_KEY` (optional).
6. Add a persistent disk mounted at `/uploads`, `/reports`, `/database` if you need
   uploaded data to survive restarts (Render's filesystem is ephemeral otherwise).

### Railway
1. Push the repo to GitHub and create a new Railway project from it.
2. Railway auto-detects Python; ensure `requirements.txt` is present.
3. Set the start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Add environment variables in the Railway dashboard (`SECRET_KEY`, AI keys).
5. Attach a Railway Volume for `/uploads`, `/reports`, `/database` for persistence.

### AWS EC2
1. Launch an Ubuntu EC2 instance; open inbound port 80/443 (and 22 for SSH).
2. SSH in, install Python 3.11+, `git`, `nginx`.
3. `git clone` the repo, create a venv, `pip install -r requirements.txt`.
4. Run with Gunicorn behind Nginx:
   ```bash
   gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
   ```
5. Configure Nginx as a reverse proxy to `127.0.0.1:8000` and set up TLS via Certbot.
6. Use `systemd` (or `supervisord`) to keep Gunicorn running and restart on boot.
7. Store `SECRET_KEY` and AI API keys as environment variables in the systemd unit
   file or an `.env` loaded via `python-dotenv`.

## License

This project is provided as a template/reference implementation. Adapt licensing
to your organization's needs before production use.
