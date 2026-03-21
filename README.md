# Proto v3 - Shop Management System

A complete Django-based POS and shop management system for multi-shop retail businesses.

## Quick Start (Windows)

1. **Install Python 3.10+** from https://python.org
2. **Double-click `install_windows.bat`** - this will:
   - Install all dependencies
   - Run database migrations
   - Create the owner account
   - Set up auto-start on Windows boot
3. **Open browser** at `http://localhost:8000`
4. **Login** with `owner` / `proto2024`

## Manual Start
```
python manage.py runserver 127.0.0.1:8000
```

## Features
- ✅ Point of Sale (POS) with day open/close
- ✅ Product management with categories and variants
- ✅ Stock management and stock-take
- ✅ Purchase orders to suppliers
- ✅ Expense tracking (daily/monthly/yearly)
- ✅ Staff management with RBAC
- ✅ Customer credit/debt tracking
- ✅ Reports and analytics (PDF export)
- ✅ Offline-capable with sync queue
- ✅ Multi-shop support with shop switching
- ✅ Daily report auto-sent on day close
- ✅ Swahili / English language toggle
- ✅ Auto-starts on Windows boot

## Default Login
- **URL**: http://localhost:8000/login/
- **Username**: owner
- **Password**: proto2024
- **Admin panel**: http://localhost:8000/admin/

## Project Structure
```
proto_v3/
├── config/          # Django settings & URLs
├── shops/           # Core: login, shop select, dashboard, day open/close
├── products/        # Products, categories, variants
├── pos/             # Point of Sale, sales processing
├── stock/           # Stock levels, movements, stock-take
├── purchases/       # Purchase orders, suppliers
├── expenses/        # Expense recording & reporting
├── staff/           # Staff, attendance, disciplinary
├── customers/       # Customers, credit management
├── reports/         # Reports, PDF export, analytics
├── sync_engine/     # Offline queue + sync to cloud
├── templates/       # All HTML templates
├── static/          # CSS, JS, images
├── start_proto.bat  # Windows launcher
└── install_windows.bat  # One-click Windows installer
```

## Tech Stack
- **Backend**: Django 5+ / Python 3.10+
- **Database**: SQLite (local) - upgradeable to PostgreSQL
- **Frontend**: Django templates + vanilla JS (no framework)
- **PDF Reports**: ReportLab
- **Offline Sync**: Custom sync queue → cloud server

## Changing the Language
Go to Settings (bottom of sidebar) and select Kiswahili or English.

## Adding a New Shop
1. Go to Django Admin: `/admin/`
2. Add a new Shop
3. Create a UserShopAccess record linking your user to the new shop

## Upgrading to PostgreSQL (Production)
Change the DATABASES setting in `config/settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'proto_v3',
        'USER': 'postgres',
        'PASSWORD': 'your-password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```
