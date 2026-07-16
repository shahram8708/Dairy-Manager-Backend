# Dairy Distribution, Vendor Billing & Payment Collection Management System

A complete web application for managing dairy product distribution, automatic billing, and payment collection across dealer/vendor networks.

## Architecture

The system consists of two independently deployable components:

- **Backend** (`backend/`) - Flask REST API with JWT authentication, SQLAlchemy ORM, and all business logic
- **Frontend** (`frontend/`) - Flask application serving Jinja2/Bootstrap templates with JavaScript API calls

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

## Quick Start

### 1. Clone and Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your settings
```

### 2. Setup Frontend

```bash
cd frontend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env - set API_BASE_URL to point to your backend
```

### 3. Run Both Components

**Terminal 1 - Backend (port 5000):**
```bash
cd backend
python app.py
```

**Terminal 2 - Frontend (port 3000):**
```bash
cd frontend
python app.py
```

Open your browser to `http://127.0.0.1:3000`

## Default Admin Credentials

On first startup, the system seeds one Admin user. Credentials come from environment variables:

| Variable | Default |
|----------|---------|
| `SEED_ADMIN_USERNAME` | `admin` |
| `SEED_ADMIN_PASSWORD` | `admin123` |

**Change these immediately in your `.env` file before deploying to production.**

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | `change-this-secret-key` |
| `JWT_SECRET_KEY` | JWT signing secret | `change-this-jwt-secret` |
| `DATABASE_URL` | SQLite database path | `sqlite:///dairy.db` |
| `SEED_ADMIN_USERNAME` | Initial admin username | `admin` |
| `SEED_ADMIN_PASSWORD` | Initial admin password | `admin123` |
| `CORS_ORIGINS` | Allowed frontend origins (comma-separated) | `http://127.0.0.1:3000` |
| `DEBUG` | Enable debug mode | `False` |

### Frontend (`frontend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | `frontend-secret` |
| `API_BASE_URL` | Backend API base URL | `http://127.0.0.1:5000/api/v1` |
| `DEBUG` | Enable debug mode | `False` |

## User Roles

### Admin
- Full access to all features
- Manage agencies, products, dealers, users, and settings
- Create and edit daily delivery entries
- Record and correct payments
- View all reports and export data

### Collector
- Read-only access to dealer information, delivery history, and reports
- **One write action**: record payment collections from dealers
- Cannot manage master data, delivery entries, or user accounts

## Key Features

- **Daily Delivery Grid** - Digital replica of the paper ledger (dealers × products) with live bill calculation
- **Automatic Billing** - Bills computed from delivered quantity × price, with price versioning
- **Payment Collection** - Real-time balance tracking with instant recalculation
- **Price History** - Historical price preservation; old bills never change when prices update
- **Reports & Export** - Daily sheets, dealer statements, outstanding balances, product sales, payment collection - all exportable to PDF and Excel
- **Audit Trail** - Every change to prices, deliveries, and payments is logged
- **Opening Balances** - Onboard dealers with pre-existing balances
- **Non-billable Items** - Track promotional/free deliveries separately from billing
- **Credit Limits** - Warnings when dealers exceed their credit limit

## Database

SQLite database is created automatically on first run. The database file location is configured via `DATABASE_URL` in the backend `.env` file (default: `backend/dairy.db`).

### Backup

Admin users can download a full database backup from **Settings → Download Backup** in the web interface.

## Currency and Date Format

- All monetary values displayed in Indian Rupees (₹ / INR)
- All dates displayed in DD/MM/YYYY format

## Production Deployment

For production, use a WSGI server like Gunicorn:

```bash
# Backend
cd backend
gunicorn app:app --bind 0.0.0.0:5000

# Frontend
cd frontend
gunicorn app:app --bind 0.0.0.0:3000
```

Ensure you:
1. Set strong, unique values for `SECRET_KEY` and `JWT_SECRET_KEY`
2. Change the default admin password
3. Set `DEBUG=False`
4. Configure `CORS_ORIGINS` to only allow your frontend's domain
