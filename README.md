# BITCRM - Flask CRM System

A production-grade Customer Relationship Management system built with Flask, featuring internationalization, responsive design, and comprehensive business tools.

## Features

- **Multi-language Support**: English (default) and Chinese (Simplified) with Flask-Babel
- **Authentication & Authorization**: Role-based access control with Flask-Login
- **Dashboard**: Key metrics with weekly year-over-year growth tracking
- **Sales Leads Management**: Import/export, filtering, and full CRUD operations
- **Pipeline Management**: Auto-calculations, revenue forecasting, and follow-up tracking
- **Task Management**: To-do items with status tracking
- **Admin Management**: User and role management
- **Responsive Design**: Bootstrap 5 for mobile-friendly interface
- **Excel Integration**: Import/export data using pandas/openpyxl

## Quick Start

### Prerequisites
- Python 3.9 or higher
- pip (Python package manager)

### Installation Steps

1. **Create a virtual environment** (recommended):
```cmd
cd C:\Users\zhang\clawd\BITCRM
python -m venv venv
venv\Scripts\activate
```

2. **Install dependencies**:
```cmd
pip install -r requirements.txt
```

3. **Set environment variables**:
```cmd
set FLASK_APP=app.py
set FLASK_ENV=development
set SECRET_KEY=your-secret-key-here-change-in-production
```

4. **Initialize the database**:
```cmd
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

5. **Run the application**:
```cmd
flask run
```

6. **Access the application**:
Open your browser and navigate to: http://localhost:5000

### Default Login Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | Bruce | bitcrm |
| Admin | Admin | bitcrm |
| Sales | Eric | bitcrm |
| Sales | Anthony | bitcrm |
| Sales | Joseph | bitcrm |
| Sales | Romeo | bitcrm |
| Sales | Uly | bitcrm |
| Sales | Lancey | bitcrm |
| Sales | Sherwin | bitcrm |
| Sales | Cean | bitcrm |
| Sales | Jeromo | bitcrm |
| Sales | Jokie | bitcrm |
| Sales | Jam | bitcrm |

## Project Structure

```
BITCRM/
├── app.py                    # Main Flask application factory
├── config.py                 # Configuration settings
├── models.py                 # SQLAlchemy models
├── routes.py                 # All route definitions
├── utils.py                  # Utility functions (Excel, calculations)
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── instance/
│   └── bitcrm.db            # SQLite database (created on first run)
├── migrations/               # Alembic migrations
├── templates/               # Jinja2 templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── leads/
│   │   ├── index.html
│   │   └── form.html
│   ├── pipeline/
│   │   ├── index.html
│   │   ├── form.html
│   │   └── follow_up_modal.html
│   ├── tasks.html
│   ├── admin/
│   │   └── users.html
│   └── partials/
├── static/
│   ├── css/
│   │   └── custom.css
│   └── js/
│       └── custom.js
└── translations/
    ├── en/
    │   └── LC_MESSAGES/
    └── zh/
        └── LC_MESSAGES/
```

## Internationalization

The application supports English (en) and Chinese (zh) languages. The language switcher is available in the top-right corner of every page. Language preference is persisted across sessions using cookies.

## Database Models

### Users
- id, username, password_hash, role, email
- Roles: admin, sales, marketing

### SalesLeads
- Name, Company, Industry, Position, Email, Mobile Number
- Requirements, Leads Status, Source, Event, Date Added, Owner, Note

### Pipeline
- Company, Industry, Name, Position, Email, Mobile Number
- Owner, Support, Product, TCV USD, Contract Term, MRC USD, OTC USD
- GP Margin, GP, MG, Est. Sign Date, Est. Act. Date
- Win Rate, Stage, Level, Date Added, Stuckpoint, Comments
- Follow-up, M1-M12 (monthly revenue forecasts)

### Tasks
- Company (optional), Owner, Content, Due Date, Status

## Key Features Usage

### Adding a Sales Lead
1. Navigate to Sales Leads page
2. Click "Add Sales Lead" button
3. Fill in all required fields
4. Choose to "Continue Adding" or "Return to List"

### Managing Pipeline
1. Pipeline entries are auto-created when a Sales Lead is marked "Qualified"
2. Manual entries can be added via "Add Pipeline" button
3. Use "Add Follow-up" to log interactions and create tasks

### Dashboard Metrics
- Weekly year-over-year growth calculated automatically
- Per-owner breakdown available
- Click "View Details" to navigate to relevant pages

### Excel Import/Export
- Download templates for data import
- Validate data before importing
- Export current filtered view to Excel

## Troubleshooting

### Database Issues
If you encounter database errors:
1. Delete the `instance/bitcrm.db` file
2. Run `flask db init` again
3. Run `flask db migrate -m "Clean migration"`
4. Run `flask db upgrade`

### Language Not Switching
- Clear browser cookies for localhost
- Ensure translations are compiled: `flask translate compile`

### Excel Import Errors
- Ensure date format is correct (e.g., "Jan 1, 2024")
- Check that source values match exactly (case-sensitive)
- Verify numeric fields contain valid numbers

## Development

### Running in Development Mode
```cmd
set FLASK_ENV=development
flask run --debug
```

### Adding New Translations
1. Add new strings to templates with `{{ _('string') }}`
2. Extract strings: `flask translate update`
3. Edit `translations/{lang}/LC_MESSAGES/messages.po`
4. Compile translations: `flask translate compile`

## License

This project is for educational and business use.

## Support

For issues or questions, please review the code documentation or contact the development team.
