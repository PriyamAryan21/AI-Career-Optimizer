<div align="center">

# 🚀 AI Career Optimizer

**An autonomous AI-powered system that keeps your Naukri.com profile perpetually optimized for maximum recruiter visibility — zero manual effort required.**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Playwright](https://img.shields.io/badge/Playwright-1.52-2EAD33?logo=playwright)](https://playwright.dev)
[![Gemini AI](https://img.shields.io/badge/Gemini_AI-Flash-4285F4?logo=google)](https://ai.google.dev)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?logo=supabase)](https://supabase.com)
[![GitHub Actions](https://img.shields.io/badge/CI/CD-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![Render](https://img.shields.io/badge/Hosted_on-Render-46E3B7?logo=render)](https://render.com)

[Live Dashboard](https://ai-career-optimizer.onrender.com) · [Report Bug](https://github.com/PriyamAryan21/AI-Career-Optimizer/issues) · [Request Feature](https://github.com/PriyamAryan21/AI-Career-Optimizer/issues)

</div>

---

## 📋 Table of Contents

- [What It Does](#-what-it-does)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [CLI Commands](#-cli-commands)
- [Dashboard](#-dashboard)
- [CI/CD Pipeline](#-cicd-pipeline)
- [Deployment](#-deployment)
- [Environment Variables](#-environment-variables)
- [Design Decisions](#-design-decisions)
- [License](#-license)

---

## 🎯 What It Does

The AI Career Optimizer is a **fully autonomous career maintenance pipeline** that:

1. **Scrapes** live job postings from Remotive, Adzuna, and JSearch APIs
2. **Analyzes** market trends using Google Gemini AI to identify in-demand skills
3. **Rewrites** your resume content (summary, experience, project bullets) to naturally incorporate trending keywords using the **STAR & Google XYZ** framework
4. **Generates** an ATS-optimized PDF resume via Playwright's Chromium PDF engine
5. **Pushes** the updated resume + a rotated headline directly to your Naukri.com profile
6. **Monitors** your profile analytics (search appearances, recruiter actions) and tracks them over time

All of this runs automatically on a **4-day cron schedule** via GitHub Actions — completely hands-free.

---

## ✨ Key Features

### 🤖 Intelligent Automation
- **AI-Powered Resume Rewriting** — Gemini rewrites your bullets using the STAR (Situation, Task, Action, Result) and Google's XYZ formula while preserving all facts and metrics
- **Headline Rotation** — Every 3rd cycle, generates a keyword-optimized profile summary using live trend data
- **JD-Tailored Resumes** — Paste any job description and get a resume specifically rewritten to match that JD
- **Smart Gap Analysis** — Compares your skills against market demand and suggests what to add or upgrade

### 🔐 Security First
- **Fernet Encryption (AES-128-CBC)** for session cookies stored in the database
- **HTTP Basic Auth** on the dashboard
- **Zero plaintext credentials** in the codebase — all secrets managed via environment variables

### 📊 Full-Stack Dashboard
- **9-tab glassmorphism UI** — Profile Overview, Performance Metrics, Skills Matrix, Hot Jobs, AI Suggestions, Resume Builder, Session Manager, System Logs, Quick Links
- **Interactive Charts** — Chart.js line graphs tracking recruiter engagement over time
- **One-Click Automation** — Trigger any CLI command directly from the dashboard

### 🛡️ Resilient Infrastructure
- **Thread-safe connection pooling** — `SimpleConnectionPool` + `threading.Lock()` for crash-free multi-threaded database access
- **Automatic log pruning** — `action_logs` table capped at 200 rows to stay within Supabase Free Tier limits
- **Exponential backoff** — All Gemini API calls retry with 15s → 30s → 60s delays, with instant failure on fatal errors
- **Graceful fallbacks** — JD resume generation falls back to a standard resume if Gemini rate limits are hit

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                           │
│              (Cron: Every 4 days @ 1:00 AM UTC)                 │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Validate │→ │ Scrape   │→ │ Analyze  │→ │ AI Rewrite    │   │
│  │ Session  │  │ Jobs     │  │ Trends   │  │ (Gemini)      │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────┬───────┘   │
│                                                     │           │
│  ┌──────────────────┐  ┌────────────────────────────▼────────┐  │
│  │ Push to Naukri   │← │ Generate PDF (Playwright)           │  │
│  │ (Headline+Resume)│  │                                     │  │
│  └──────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Supabase (PostgreSQL)                         │
│                                                                 │
│  action_logs │ session_state │ profile_metrics │ trend_data     │
│  job_postings │ suggestions_queue │ skill_inventory              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Render.com (Dashboard)                        │
│          Flask + Waitress WSGI + Vanilla JS + Chart.js          │
│                                                                 │
│  Profile │ Metrics │ Skills │ Jobs │ Resume │ Logs │ Quick Links │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.12 | Core runtime |
| **AI** | Google Gemini (Flash) | Resume rewriting, trend analysis, gap analysis, job scoring |
| **Browser Automation** | Playwright + Chromium | Naukri login, headline update, resume upload, PDF generation |
| **Web Framework** | Flask + Waitress | Dashboard backend (WSGI server, 4 threads) |
| **Frontend** | Vanilla HTML/CSS/JS + Chart.js | Glassmorphism dark-mode SPA |
| **Database** | Supabase (PostgreSQL) | Profile metrics, action logs, session state, job postings |
| **Encryption** | cryptography (Fernet) | AES-128-CBC encryption for stored session cookies |
| **CI/CD** | GitHub Actions | Scheduled automation (cron) + manual dispatch |
| **Hosting** | Render.com | Free-tier dashboard deployment |
| **Job APIs** | Remotive, Adzuna, JSearch | Multi-source job aggregation |
| **Notifications** | SMTP (smtplib) | Email alerts on session cookie expiry |

---

## 📁 Project Structure

```
AI-Career-Optimizer/
├── .github/
│   └── workflows/
│       ├── career-optimizer.yml   # Main automation pipeline (4-day cron)
│       └── keep-alive.yml         # Prevents GitHub from disabling the cron
├── config/
│   ├── __init__.py
│   └── settings.py                # Central config, env vars, Gemini retry logic
├── core/
│   ├── auth.py                    # Naukri login, session validation, cookie management
│   ├── freshness_manager.py       # Full automation orchestrator
│   ├── headline_rotator.py        # AI headline generation + Naukri DOM update
│   ├── resume_generator.py        # PDF generation + Naukri upload
│   ├── analytics_scraper.py       # Naukri performance metrics scraper
│   └── notification.py            # SMTP email alerts
├── dashboard/
│   ├── app.py                     # Flask backend (20+ API routes)
│   └── static/
│       └── index.html             # Full SPA frontend (9 tabs)
├── database/
│   ├── db_init.py                 # Table creation scripts
│   └── models.py                  # All DB operations, connection pooling, log pruning
├── intelligence/
│   ├── job_feed.py                # Multi-API job aggregation + AI scoring
│   ├── trend_analyzer.py          # Gemini-powered skill demand analysis
│   ├── gap_analyzer.py            # Profile vs. market gap detection
│   └── keyword_injector.py        # AI content rewriting engine
├── templates/
│   └── resume_template.py         # HTML resume template (ATS-optimized)
├── notifications/
│   └── notifier.py                # Email notification dispatcher
├── main.py                        # CLI entry point (all commands)
├── master_profile.yaml            # Single source of truth for profile data
├── requirements.txt               # Python dependencies
├── Procfile                       # Render deployment config
└── .env                           # Local environment variables (gitignored)
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- A [Supabase](https://supabase.com) account (free tier works)
- A [Google AI Studio](https://aistudio.google.com) API key (free tier works)
- A Naukri.com account

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/PriyamAryan21/AI-Career-Optimizer.git
cd AI-Career-Optimizer

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Generate a Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 6. Create your .env file (see Environment Variables section below)
copy .env.example .env       # then fill in your values

# 7. Initialize the database tables
python main.py --db-init

# 8. Log in to Naukri (opens a browser window for manual login)
python main.py --login

# 9. Start the dashboard
python dashboard/app.py
```

The dashboard will be available at `http://localhost:5000`.

---

## 💻 CLI Commands

All commands are executed via `main.py` and automatically log their results to the `action_logs` database table.

| Command | Description |
|---------|-------------|
| `python main.py` | Run the **full automation cycle** (validate → scrape → trends → rewrite → generate PDF → push to Naukri) |
| `python main.py --login` | Open a Chromium window to manually log in to Naukri and capture session cookies |
| `python main.py --validate` | Fast HTTP-based session cookie validation (< 2 seconds) |
| `python main.py --scrape` | Fetch raw job listings from all configured API sources |
| `python main.py --trends` | Scrape jobs + run Gemini trend analysis to identify in-demand skills |
| `python main.py --resume` | Generate a PDF resume from `master_profile.yaml` |
| `python main.py --gaps` | Run AI gap analysis (your skills vs. market demand) |
| `python main.py --push` | Force-push the latest resume + rotate headline on Naukri |
| `python main.py --jobs` | Run AI job scoring to generate a ranked Hot Jobs feed |
| `python main.py --db-init` | Create all required database tables in Supabase |

---

## 🖥️ Dashboard

The dashboard is a premium, glassmorphism-styled dark-mode single-page application with **9 interactive tabs**:

| Tab | Description |
|-----|-------------|
| **Profile Overview** | View and edit your `master_profile.yaml` as beautifully rendered cards. Includes a raw YAML editor modal. |
| **Performance Metrics** | KPI cards (search appearances, recruiter actions) + interactive Chart.js line graphs. |
| **Skills Matrix** | Add, delete, and promote skills. View AI-generated skill suggestions with Accept/Dismiss buttons. |
| **Hot Jobs** | AI-scored job feed ranked by match percentage with direct "Apply Now" links. |
| **AI Suggestions** | Pending profile improvement suggestions from the gap analyzer. |
| **Resume Builder** | Generate standard or JD-tailored PDFs. AI Smart Add for projects, experience, achievements, and extracurriculars using STAR & Google XYZ frameworks. |
| **Session Manager** | View session health and manually update Naukri cookies. |
| **System Logs** | Paginated audit trail of all automation actions with color-coded status badges. |
| **Quick Links** | One-click trigger cards for Validate, Push, Gaps, Trends, Scrape, and Score Jobs. |

---

## ⚙️ CI/CD Pipeline

### Automated Schedule
The GitHub Actions workflow (`.github/workflows/career-optimizer.yml`) runs automatically every **4 days at 1:00 AM UTC** (6:30 AM IST).

### Manual Dispatch
You can also trigger it manually from the GitHub Actions tab with a mode selector:

```
Modes: full | resume | jobs | gaps | validate | scrape | trends | push
```

### Keep-Alive
A separate workflow (`.github/workflows/keep-alive.yml`) prevents GitHub from auto-disabling the cron job due to 60-day repository inactivity.

---

## 🌐 Deployment

### Dashboard (Render.com)

1. Connect your GitHub repository to [Render](https://render.com)
2. Set the **Build Command**: `pip install -r requirements.txt && playwright install chromium --with-deps`
3. Set the **Start Command**: `gunicorn dashboard.app:app`
4. Add all environment variables in the Render dashboard
5. Deploy!

### Automation (GitHub Actions)

1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**
2. Add all environment variables as repository secrets (see table below)
3. The cron job will automatically start running on schedule

---

## 🔑 Environment Variables

Create a `.env` file in the project root with the following variables:

| Variable | Description | Required For |
|----------|-------------|--------------|
| `GEMINI_API_KEY` | Google Gemini API key | AI features |
| `GEMINI_MODEL` | Model name (default: `gemini-1.5-flash`) | AI features |
| `DATABASE_URL` | Supabase PostgreSQL connection string | Database |
| `NAUKRI_EMAIL` | Naukri.com login email | Browser automation |
| `NAUKRI_PASSWORD` | Naukri.com login password | Browser automation |
| `FERNET_KEY` | AES encryption key for cookie storage | Security |
| `DASHBOARD_USERNAME` | Dashboard HTTP Basic Auth username | Dashboard |
| `DASHBOARD_PASSWORD` | Dashboard HTTP Basic Auth password | Dashboard |
| `SMTP_HOST` | Email server hostname (e.g., `smtp.gmail.com`) | Notifications |
| `SMTP_PORT` | Email server port (e.g., `587`) | Notifications |
| `SMTP_EMAIL` | Sender email address | Notifications |
| `SMTP_PASSWORD` | Sender email app password | Notifications |
| `NOTIFICATION_EMAIL` | Recipient email for alerts | Notifications |
| `ADZUNA_APP_ID` | Adzuna API application ID | Job scraping |
| `ADZUNA_APP_KEY` | Adzuna API key | Job scraping |
| `RAPIDAPI_KEY` | RapidAPI key (JSearch) | Job scraping |
| `UPDATE_FREQUENCY_DAYS` | Automation cycle interval (default: `4`) | Scheduling |
| `JITTER_HOURS` | Random delay range (default: `3`) | Anti-detection |
| `TARGET_ROLES` | Comma-separated target job titles | Job scraping |
| `GITHUB_TOKEN` | GitHub PAT for remote CI trigger | Dashboard → CI |
| `GITHUB_REPO` | Repository slug (e.g., `user/repo`) | Dashboard → CI |

---

## 🧠 Design Decisions

### Why Playwright for PDF generation instead of WeasyPrint?
WeasyPrint requires native system libraries (GTK, Cairo, Pango) that are notoriously difficult to install in CI/CD environments. Playwright was already a mandatory dependency for browser automation, and its built-in `page.pdf()` API produces pixel-perfect output with superior CSS support (flexbox, grid, `break-inside: avoid`).

### Why STAR & Google XYZ for bullet points?
The **STAR** (Situation, Task, Action, Result) framework combined with Google's **XYZ formula** ("Accomplished [X] as measured by [Y], by doing [Z]") is the gold standard used by FAANG recruiters. It forces every bullet point to lead with measurable impact rather than passive task descriptions.

### Why SimpleConnectionPool instead of ThreadedConnectionPool?
`psycopg2.pool.ThreadedConnectionPool` was causing intermittent "trying to put unkeyed connection" errors under Waitress's multi-threaded WSGI server. Wrapping `SimpleConnectionPool` with a `threading.Lock()` provides deterministic, crash-free connection management.

### Why not automate Naukri's Skills section?
Naukri uses a proprietary autocomplete dropdown that only accepts skills from their internal taxonomy. The component uses obfuscated CSS class names that change across deployments, making reliable automation infeasible without risking profile corruption.

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<div align="center">

**Built with ❤️ by [Priyam Aryan](https://github.com/PriyamAryan21)**

*If this project helped you land interviews, give it a ⭐!*

</div>
