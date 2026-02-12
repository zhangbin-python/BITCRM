"""
BITCRM Main Application Factory
Flask application factory and initialization.
"""
import os
from datetime import date, datetime
from flask import Flask, request
from flask_babel import Babel
from extensions import db, login_manager, babel, migrate

# Configure login manager
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

def get_locale():
    """Get user preferred language."""
    lang = request.cookies.get('lang')
    if lang and lang in ['en', 'zh']:
        return lang
    return request.accept_languages.best_match(['en', 'zh'])

def get_timezone():
    """Get user preferred timezone."""
    return 'UTC'

def create_app(config_class=None):
    """Application factory pattern."""
    app = Flask(__name__)
    
    # Load configuration
    if config_class is None:
        config_class = os.environ.get('FLASK_CONFIG_CLASS') or 'config.DevelopmentConfig'
    
    if isinstance(config_class, str):
        from importlib import import_module
        try:
            module_path, config_name = config_class.rsplit('.', 1)
            config_module = import_module(module_path)
            config = getattr(config_module, config_name)
        except (ImportError, ValueError):
            # Fallback if config import fails
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bitcrm.db'
            app.config['SECRET_KEY'] = 'dev-key'
            config = None
    else:
        config = config_class
    
    if config:
        app.config.from_object(config)
    
    # Set cache type if not configured (for development)
    if app.config.get('CACHE_TYPE') is None:
        app.config['CACHE_TYPE'] = 'SimpleCache'
    
    # Initialize extensions with app
    babel.init_app(app, locale_selector=get_locale, timezone_selector=get_timezone)
    login_manager.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Initialize Flask-Caching
    from extensions import cache
    cache.init_app(app)
    
    # Register HTTP cache headers (must be after app is created)
    @app.after_request
    def add_cache_headers(response):
        """
        Add HTTP cache headers for better performance.
        Layer 1: Browser/CDN caching
        """
        from flask import request
        # Skip cache headers for non-GET requests
        if request.method != 'GET':
            return response
        
        # Static resources: 1 year cache
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # API endpoints: 5 minutes cache
        elif request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, max-age=300'
        
        # HTML pages: No cache (always verify with server)
        elif response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        # Security headers
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    # Register blueprints and initialize data
    with app.app_context():
        # 1. Register blueprints
        from routes import main_bp, leads_bp, pipeline_bp, tasks_bp, admin_bp, api_bp
        app.register_blueprint(main_bp)
        app.register_blueprint(leads_bp, url_prefix='/leads')
        app.register_blueprint(pipeline_bp, url_prefix='/pipeline')
        app.register_blueprint(tasks_bp, url_prefix='/tasks')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(api_bp)
        
        # 2. Create folders
        os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
        os.makedirs(app.config.get('EXCEL_TEMPLATES_FOLDER', 'templates/excel'), exist_ok=True)
        
        # 3. Create database tables (import models to register them)
        from models import User
        
        # 3.1 Add dashboard_filters column if it doesn't exist
        from sqlalchemy import text
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN dashboard_filters TEXT'))
            db.session.commit()
            print("[OK] Added dashboard_filters column")
        except Exception:
            db.session.rollback()
            print("[INFO] dashboard_filters column might already exist")
        
        # 3.2 Create all tables
        db.create_all()
        
        # 4. Handle existing users - add default dashboard_filters value
        users = User.query.all()
        for user in users:
            if user.dashboard_filters is None:
                user.dashboard_filters = '{}'
        if users:
            db.session.commit()
        
        # 5. Initialize default users (only if users table is empty)
        # Use file lock to prevent race condition in gunicorn
        lock_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', '.users_initialized.lock')
        os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
        
        # Check if already initialized (gunicorn workers)
        skip_initialization = os.path.exists(lock_file_path)
        
        try:
            # Double-check: see if admin user exists
            admin_exists = User.query.filter_by(username='Bruce').first() is not None
            
            if not skip_initialization and not admin_exists:
                # First worker - create users
                open(lock_file_path, 'w').close()  # Create lock file
                
                print("[INFO] Creating default users...")
                admin_users = [
                    ('Bruce', 'bruce@example.com', 'bitcrm', 'admin'),
                    ('Admin', 'admin@example.com', 'bitcrm', 'admin'),
                ]
                sales_users = [
                    ('Eric', 'eric@example.com', 'bitcrm', 'sales'),
                    ('Anthony', 'anthony@example.com', 'bitcrm', 'sales'),
                    ('Joseph', 'joseph@example.com', 'bitcrm', 'sales'),
                    ('Romeo', 'romeo@example.com', 'bitcrm', 'sales'),
                    ('Uly', 'uly@example.com', 'bitcrm', 'sales'),
                    ('Lancey', 'lancey@example.com', 'bitcrm', 'sales'),
                    ('Sherwin', 'sherwin@example.com', 'bitcrm', 'sales'),
                    ('Cean', 'cean@example.com', 'bitcrm', 'sales'),
                    ('Jeromo', 'jeromo@example.com', 'bitcrm', 'sales'),
                    ('Jokie', 'jokie@example.com', 'bitcrm', 'sales'),
                    ('Jam', 'jam@example.com', 'bitcrm', 'sales'),
                ]
                marketing_users = [
                    ('Romeo_m', 'romeo_m@example.com', 'bitcrm', 'marketing'),
                    ('Lancey_m', 'lancey_m@example.com', 'bitcrm', 'marketing'),
                ]
                
                created = 0
                for username, email, password, role in admin_users + sales_users + marketing_users:
                    if not User.query.filter_by(username=username).first():
                        user = User(username=username, email=email, role=role)
                        user.set_password(password)
                        db.session.add(user)
                        created += 1
                
                db.session.commit()
                print(f"[OK] Created {created} default users")
            else:
                print("[OK] Users already exist, skipping creation")
        except Exception as e:
            db.session.rollback()
            # Remove lock file on error so retry can happen
            try:
                os.remove(lock_file_path)
            except:
                pass
            print(f"[WARN] User initialization failed: {e}")
    
    # =========================================================================
    # WEEKLY METRICS AUTO-UPDATE via SQLAlchemy Events
    # =========================================================================
    
    from sqlalchemy import event
    from datetime import timedelta
    from utils import (
        calculate_quarter_revenue,
        get_current_quarter_dates,
        get_next_quarter_dates
    )
    from models import WeeklyMetrics
    
    def get_week_start(ref_date=None):
        """获取本周一日期"""
        if ref_date is None:
            ref_date = date.today()
        return ref_date - timedelta(days=ref_date.weekday())
    
    def recalculate_weekly_metrics(owner_id, ref_date=None):
        """重新计算并覆盖写入 weekly_metrics"""
        if ref_date is None:
            ref_date = date.today()
        
        week_start = get_week_start(ref_date)
        quarter_start, quarter_end = get_current_quarter_dates(ref_date)
        next_qtr_start, next_qtr_end = get_next_quarter_dates(ref_date)
        
        # 全公司汇总 = 直接求和所有用户的 weekly_metrics
        if owner_id is None:
            all_user_metrics = WeeklyMetrics.query.filter_by(week_start=week_start).all()
            
            leads_count = sum(m.leads_count or 0 for m in all_user_metrics)
            qualified_leads_count = sum(m.qualified_leads_count or 0 for m in all_user_metrics)
            pipeline_count = sum(m.pipeline_count or 0 for m in all_user_metrics)
            tcv = sum(m.tcv or 0 for m in all_user_metrics)
            
            # 季度收入直接求和（避免重复计算）
            current_qtr_rev = sum(m.current_qtr_revenue or 0 for m in all_user_metrics)
            next_qtr_rev = sum(m.next_qtr_revenue or 0 for m in all_user_metrics)
            
            # 覆盖写入全公司汇总
            record = WeeklyMetrics.query.filter_by(
                owner_id=None,
                week_start=week_start
            ).first()
            
            if not record:
                record = WeeklyMetrics(owner_id=None, week_start=week_start)
                db.session.add(record)
            
            record.leads_count = leads_count
            record.qualified_leads_count = qualified_leads_count
            record.pipeline_count = pipeline_count
            record.tcv = tcv
            record.current_qtr_revenue = current_qtr_rev
            record.next_qtr_revenue = next_qtr_rev
            record.updated_at = datetime.utcnow()
            
            db.session.commit()
            return
        
        # 单个用户计算（从 Pipeline/Leads 表）
        from models import Pipeline, SalesLead
        pipelines = Pipeline.query.filter(
            Pipeline.owner_id == owner_id,
            Pipeline.stage != '6b) Deal Lost'
        ).all()
        
        leads_count = SalesLead.query.filter(
            SalesLead.owner_id == owner_id,
            SalesLead.leads_status != 'Unqualified'
        ).count()
        
        qualified_leads_count = SalesLead.query.filter(
            SalesLead.owner_id == owner_id,
            SalesLead.leads_status == 'Qualified'
        ).count()
        
        pipeline_count = len(pipelines)
        tcv = sum(p.tcv_usd or 0 for p in pipelines)
        
        current_qtr_rev = calculate_quarter_revenue(pipelines, quarter_start, quarter_end)
        next_qtr_rev = calculate_quarter_revenue(pipelines, next_qtr_start, next_qtr_end)
        
        # 覆盖写入
        record = WeeklyMetrics.query.filter_by(
            owner_id=owner_id,
            week_start=week_start
        ).first()
        
        if not record:
            record = WeeklyMetrics(owner_id=owner_id, week_start=week_start)
            db.session.add(record)
        
        record.leads_count = leads_count
        record.qualified_leads_count = qualified_leads_count
        record.pipeline_count = pipeline_count
        record.tcv = tcv
        record.current_qtr_revenue = current_qtr_rev
        record.next_qtr_revenue = next_qtr_rev
        record.updated_at = datetime.utcnow()
        
        db.session.commit()
    
    def recalculate_all_weekly_metrics(ref_date=None):
        """重新计算所有用户的 weekly_metrics（包括全公司汇总）"""
        if ref_date is None:
            ref_date = date.today()
        
        # 重新计算全公司汇总
        recalculate_weekly_metrics(owner_id=None, ref_date=ref_date)
        
        # 重新计算每个活跃用户
        from models import User
        users = User.query.filter_by(is_active=True).all()
        for user in users:
            recalculate_weekly_metrics(owner_id=user.id, ref_date=ref_date)
    
    @event.listens_for(db.session, 'after_commit')
    def after_commit_update_weekly_metrics(session):
        """监听数据库提交，自动更新 weekly_metrics"""
        # 跳过非主应用上下文
        if not hasattr(app, 'app_context') or not app.app_context:
            return
        
        try:
            owners_to_update = set()
            
            # 遍历新增对象
            for obj in session.new:
                if hasattr(obj, 'owner_id') and obj.owner_id:
                    owners_to_update.add(obj.owner_id)
            
            # 遍历修改对象
            for obj in session.dirty:
                if hasattr(obj, 'owner_id') and obj.owner_id:
                    owners_to_update.add(obj.owner_id)
            
            # 遍历删除对象
            for obj in session.deleted:
                if hasattr(obj, 'owner_id') and obj.owner_id:
                    owners_to_update.add(obj.owner_id)
            
            # 更新所有受影响的 owner
            for owner_id in owners_to_update:
                try:
                    recalculate_weekly_metrics(owner_id)
                except Exception as e:
                    print(f"[WARN] Failed to update weekly metrics for owner {owner_id}: {e}")
            
            # 重新计算全公司汇总（汇总所有用户的 metrics）
            if owners_to_update:
                try:
                    recalculate_weekly_metrics(None)
                except Exception as e:
                    print(f"[WARN] Failed to update company weekly metrics: {e}")
        
        except Exception as e:
            print(f"[WARN] Error in after_commit_update_weekly_metrics: {e}")
    
    # =========================================================================
    # END WEEKLY METRICS
    # =========================================================================
    
    # =========================================================================
    # =========================================================================
    
    # Register template filters
    @app.template_filter('format_date')
    def format_date(date_obj):
        return date_obj.strftime('%b %d, %Y') if date_obj else ''

    @app.template_filter('format_currency')
    def format_currency(value):
        return f"${value:,}" if value is not None else '$0'

    @app.template_filter('format_percent')
    def format_percent(value):
        return f"{value * 100:.0f}%" if value is not None else '0%'
    
    return app

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))
