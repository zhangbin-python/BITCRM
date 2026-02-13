"""
BITCRM Database Models
SQLAlchemy models for the CRM system.
"""
from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from dateutil.relativedelta import relativedelta
from sqlalchemy import event
from contextlib import contextmanager
import calendar


# ============================================================================
# USER MODEL
# ============================================================================

class User(UserMixin, db.Model):
    """User model for authentication and authorization."""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='sales')  # admin, sales, marketing
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Column preferences for datatable views (stored as JSON)
    # Format: {"leads": {"columns": ["name", "company", "status"], "order": 1}, ...}
    column_preferences = db.Column(db.Text, nullable=True, default='{}')
    
    # Dashboard filter preferences (stored as JSON)
    # Format: {"owners": [1, 2, 3], "stages": ["1) Prospecting", "2) Qualification"], ...}
    dashboard_filters = db.Column(db.Text, nullable=True, default='{}')
    
    # Relationships
    owned_sales_leads = db.relationship('SalesLead', 
                                         foreign_keys='SalesLead.owner_id',
                                         backref='owner', lazy='dynamic')
    owned_pipelines = db.relationship('Pipeline', 
                                       foreign_keys='Pipeline.owner_id',
                                       backref='owner', lazy='dynamic')
    supported_pipelines = db.relationship('Pipeline', 
                                           secondary='pipeline_support',
                                           backref='support_team', lazy='dynamic')
    tasks = db.relationship('Task', backref='owner', lazy='dynamic')
    
    def set_password(self, password):
        """Set user password with hashing."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if password matches."""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        """Check if user has admin role."""
        return self.role.lower() == 'admin'
    
    def is_marketing(self):
        """Check if user has marketing role."""
        return self.role.lower() == 'marketing'
    
    def can_access_leads(self):
        """Check if user can access sales leads."""
        # admin, marketing, and sales can all access leads
        return self.role.lower() in ['admin', 'marketing', 'sales']
    
    def can_view_all_leads(self):
        """Check if user can view all leads (not just own)."""
        return self.role.lower() in ['admin', 'marketing']
    
    def can_access_pipeline(self, pipeline):
        """Check if user can access a specific pipeline."""
        if self.is_admin():
            return True
        # Check if user is owner or in support team
        if pipeline.owner_id == self.id:
            return True
        if self in pipeline.support_team:
            return True
        return False
    
    def get_full_name(self):
        """Return user's full name (username for now)."""
        return self.username
    
    def get_column_preferences(self, page):
        """Get user's column preferences for a specific page."""
        import json
        try:
            prefs = json.loads(self.column_preferences or '{}')
            return prefs.get(page, {})
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_column_preferences(self, page, columns, order=None):
        """Set user's column preferences for a specific page."""
        import json
        try:
            prefs = json.loads(self.column_preferences or '{}')
            prefs[page] = {
                'columns': columns,
                'order': order
            }
            self.column_preferences = json.dumps(prefs)
        except (json.JSONDecodeError, TypeError):
            self.column_preferences = json.dumps({page: {'columns': columns, 'order': order}})
    
    def get_dashboard_filters(self):
        """Get user's dashboard filter preferences."""
        import json
        try:
            return json.loads(self.dashboard_filters or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_dashboard_filters(self, filters):
        """Set user's dashboard filter preferences."""
        import json
        try:
            self.dashboard_filters = json.dumps(filters)
        except (TypeError):
            self.dashboard_filters = '{}'
    
    def __repr__(self):
        return f'<User {self.username}>'


# ============================================================================
# SALES LEAD MODEL
# ============================================================================

class SalesLead(db.Model):
    """Sales Lead model for tracking potential customers."""
    
    __tablename__ = 'sales_leads'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic information
    name = db.Column(db.String(120), nullable=False)
    company = db.Column(db.String(200), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    position = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    mobile_number = db.Column(db.String(50), nullable=True)
    requirements = db.Column(db.Text, nullable=True)
    
    # Status and categorization
    leads_status = db.Column(db.String(50), nullable=False, default='Waiting to be Contacted', index=True)
    source = db.Column(db.String(50), nullable=True)
    event = db.Column(db.String(200), nullable=True)
    
    # Tracking
    date_added = db.Column(db.Date, nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    note = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to Pipeline
    pipeline = db.relationship('Pipeline', backref='sales_lead', uselist=False)
    
    # Valid status options
    STATUS_OPTIONS = [
        'Qualified',
        'Waiting for Response',
        'Unqualified',
        'Waiting to be Contacted'
    ]
    
    # Valid source options
    SOURCE_OPTIONS = [
        'Website',
        'Referral',
        'Email Campaign',
        'Social Media',
        'Event',
        'Trade Show',
        'Advertisement',
        'Partner',
        'Direct Inquiry',
        'BFSI',
        'Channel',
        'Others'
    ]
    
    def get_status_color(self):
        """Return Bootstrap color class based on status."""
        status_colors = {
            'Qualified': 'success',
            'Waiting for Response': 'warning',
            'Unqualified': 'danger',
            'Waiting to be Contacted': 'secondary'
        }
        return status_colors.get(self.leads_status, 'secondary')
    
    def validate_field(self, field_name, value):
        """
        Validate a field value before updating.
        Returns (is_valid, error_message, cleaned_value)
        """
        import re
        from datetime import datetime
        
        if field_name == 'name':
            if not value or not value.strip():
                return False, '姓名不能为空', None
            return True, None, value.strip()[:120]
        
        elif field_name == 'company':
            return True, None, value.strip()[:200] if value else None
        
        elif field_name == 'industry':
            return True, None, value.strip()[:100] if value else None
        
        elif field_name == 'position':
            return True, None, value.strip()[:100] if value else None
        
        elif field_name == 'email':
            if value and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value.strip()):
                return False, '邮箱格式无效', None
            return True, None, value.strip()[:120] if value else None
        
        elif field_name == 'mobile_number':
            if value and not re.match(r'^[\d\s\-\(\)\+]+$', value):
                return False, '电话号码格式无效', None
            return True, None, value.strip()[:50] if value else None
        
        elif field_name == 'requirements':
            return True, None, value.strip() if value else None
        
        elif field_name == 'leads_status':
            if value not in self.STATUS_OPTIONS:
                return False, f'状态必须是以下之一: {", ".join(self.STATUS_OPTIONS)}', None
            return True, None, value
        
        elif field_name == 'source':
            if value and value not in self.SOURCE_OPTIONS:
                return False, f'来源必须是以下之一: {", ".join(self.SOURCE_OPTIONS)}', None
            return True, None, value if value else None
        
        elif field_name == 'event':
            return True, None, value.strip()[:200] if value else None
        
        elif field_name == 'date_added':
            if not value:
                return True, None, None
            from extensions import db
            try:
                if isinstance(value, str):
                    parsed_date = datetime.strptime(value, '%Y-%m-%d').date()
                else:
                    parsed_date = value
                return True, None, parsed_date
            except ValueError:
                return False, '日期格式无效，请使用 YYYY-MM-DD 格式', None
        
        elif field_name == 'owner_id':
            from extensions import db
            if value:
                owner = db.session.get(User, value)
                if not owner:
                    return False, '所选负责人不存在', None
            return True, None, value
        
        elif field_name == 'note':
            return True, None, value.strip() if value else None
        
        else:
            return False, f'字段 {field_name} 不允许编辑', None
    
    def convert_to_pipeline(self):
        """Convert lead to pipeline when qualified."""
        if self.pipeline:
            return self.pipeline
        
        # Create new pipeline entry
        pipeline = Pipeline(
            name=self.name,
            company=self.company,
            industry=self.industry,
            position=self.position,
            email=self.email,
            mobile_number=self.mobile_number,
            product=self.requirements,
            date_added=date.today(),
            owner_id=self.owner_id,
            stage='2) Lead Qualified',
            sales_lead_id=self.id
        )
        return pipeline
    
    def __repr__(self):
        return f'<SalesLead {self.name}>'


# ============================================================================
# PIPELINE MODEL
# ============================================================================

class Pipeline(db.Model):
    """Pipeline model for tracking sales opportunities."""
    
    __tablename__ = 'pipeline'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic information
    name = db.Column(db.String(120), nullable=False)
    company = db.Column(db.String(200), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    position = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    mobile_number = db.Column(db.String(50), nullable=True)
    
    # Ownership
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sales_lead_id = db.Column(db.Integer, db.ForeignKey('sales_leads.id'), nullable=True, index=True)
    
    # Support team (many-to-many relationship)
    
    # Product and value
    product = db.Column(db.String(200), nullable=True)
    tcv_usd = db.Column(db.Float, default=0)  # Total Contract Value (4 decimal places)
    contract_term_yrs = db.Column(db.Integer, default=1)  # Contract Term in Years
    mrc_usd = db.Column(db.Float, default=0)  # Monthly Recurring Cost (4 decimal places)
    otc_usd = db.Column(db.Float, default=0)  # One-Time Cost (4 decimal places)
    
    # Profitability
    gp_margin = db.Column(db.Float, default=0.0)  # Gross Profit Margin (4 decimal places)
    gp = db.Column(db.Float, default=0)  # Gross Profit (4 decimal places)
    mg = db.Column(db.String(50), nullable=True)  # Margin Grade
    
    # Dates
    est_sign_date = db.Column(db.Date, nullable=True, index=True)
    est_act_date = db.Column(db.Date, nullable=True)  # Estimated Activation Date
    award_date = db.Column(db.Date, nullable=True)  # Award date
    proposal_sent_date = db.Column(db.Date, nullable=True)  # Proposal Sent Date
    
    # Probability and stage
    win_rate = db.Column(db.Float, default=0.0)
    stage = db.Column(db.String(50), default='Prospecting', index=True)
    level = db.Column(db.String(50), default='Stretch')
    
    # Tracking
    date_added = db.Column(db.Date, default=date.today)
    stuckpoint = db.Column(db.Text, nullable=True)
    comments = db.Column(db.Text, nullable=True)
    follow_up = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Follow-up methods
    def get_latest_followup_date(self):
        """Extract the latest follow-up date from follow_up text field.
        
        Format: Follow-up, YYYY-MM-DD HH:MM: text
        
        Returns: date object or None
        """
        if not self.follow_up or str(self.follow_up).strip() == '':
            return None
        
        import re
        from datetime import datetime
        
        lines = self.follow_up.split('\n')
        
        # Regex to match "Follow-up, YYYY-MM-DD"
        # Does not match "To-do" (that's a task, not a follow-up)
        pattern = re.compile(r'Follow-up,\s+(\d{4}-\d{2}-\d{2})')
        
        latest_date = None
        
        for line in lines:
            match = pattern.search(line)
            if match:
                date_str = match.group(1)  # YYYY-MM-DD
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
                except ValueError:
                    # Skip invalid dates
                    pass
        
        return latest_date
    
    def get_followup_days_ago(self):
        """Calculate days since latest follow-up.
        
        Returns: days count or None
        """
        from datetime import date
        
        latest_date = self.get_latest_followup_date()
        if latest_date:
            return (date.today() - latest_date).days
        return None
    
    def get_followup_color_class(self):
        """Return background color class based on days since follow-up.

        Rules:
        - No follow-up: red (bg-danger), display "无跟进"
        - <=10 days: green (bg-success)
        - 11-30 days: yellow (bg-warning)
        - >30 days: red (bg-danger)

        Returns: Bootstrap class string
        """
        days = self.get_followup_days_ago()
        if days is None:
            return 'bg-danger'  # No follow-up: red
        elif days <= 10:
            return 'bg-success'  # Green
        elif days <= 30:
            return 'bg-warning'  # Yellow
        else:
            return 'bg-danger'   # Red

    def get_followup_display(self):
        """Return display text for follow-up.

        Returns: "N days ago" for follow-ups, or "No follow-up" if none.
        """
        days = self.get_followup_days_ago()
        if days is None:
            return 'No follow-up'
        elif days == 0:
            return 'Today'
        elif days == 1:
            return '1 day ago'
        else:
            return f'{days} days ago'

    def get_tcv(self):
        """Calculate Total Contract Value."""
        mrc = self.mrc_usd if self.mrc_usd else 0
        otc = self.otc_usd if self.otc_usd else 0
        term = self.contract_term_yrs if self.contract_term_yrs else 0
        return (mrc * 12 * term) + otc
    
    def get_acv(self):
        """Calculate Annual Contract Value."""
        mrc = self.mrc_usd if self.mrc_usd else 0
        return mrc * 12
    
    def get_gp(self):
        """Calculate Gross Profit."""
        tcv = self.tcv_usd if self.tcv_usd else 0
        margin = self.gp_margin if self.gp_margin else 0
        return int(tcv * margin)
    
    def is_won(self):
        """Check if deal is won."""
        return self.stage == '6a) Deal Won'
    
    def is_lost(self):
        """Check if deal is lost."""
        return self.stage == '6b) Deal Lost'
    
    def is_active(self):
        """Check if deal is still active (not won or lost)."""
        return self.stage not in ['6a) Deal Won', '6b) Deal Lost']
    
    def get_stage_color(self):
        """Return Bootstrap color class based on stage (avoiding red/yellow)."""
        stage_colors = {
            '1) Prospecting': 'secondary',   # Gray-blue
            '2) Lead Qualified': 'info',     # Blue
            '3) Demo/Meeting': 'primary',    # Blue
            '4) Proposal Submitted': 'primary', # Blue
            '5) Negotiation': 'warning',     # Orange (not yellow)
            '6a) Deal Won': 'success',      # Green
            '6b) Deal Lost': 'secondary',    # Gray (not red)
            '7) Activated': 'success'        # Green
        }
        return stage_colors.get(self.stage, 'secondary')
    
    def add_followup(self, followup_text, stuckpoint_text=None, todo_text=None, 
                     todo_due_date=None, user_id=None):
        """Add follow-up entry."""
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Append to follow-up field
        if self.follow_up:
            self.follow_up += f"\nFollow-up, {timestamp}: {followup_text}"
        else:
            self.follow_up = f"Follow-up, {timestamp}: {followup_text}"
        
        # Update stuckpoint if provided
        if stuckpoint_text:
            self.stuckpoint = stuckpoint_text
        
        # Create task if todo provided
        if todo_text and todo_due_date and user_id:
            task = Task(
                content=todo_text,
                due_date=todo_due_date,
                owner_id=user_id,
                pipeline_id=self.id,
                company=self.company
            )
            db.session.add(task)
            # Append to follow-up
            todo_timestamp = datetime.now().strftime('%Y-%m-%d')
            self.follow_up += f"\nTo-do, {todo_timestamp}: {todo_text} by {todo_due_date}"
    
    def __repr__(self):
        return f'<Pipeline {self.name}>'


# ============================================================================
# SUPPORT TABLE FOR MANY-TO-MANY RELATIONSHIP
# ============================================================================

pipeline_support = db.Table('pipeline_support',
    db.Column('pipeline_id', db.Integer, db.ForeignKey('pipeline.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)


# ============================================================================
# TASK MODEL
# ============================================================================

class Task(db.Model):
    """Task model for tracking to-do items from follow-ups."""
    
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Task content
    content = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    
    # Status
    status = db.Column(db.String(20), default='In Progress')  # In Progress, Overdue, Completed
    
    # Relationships
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipeline.id'), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_status_color(self):
        """Return Bootstrap color class based on status."""
        status_colors = {
            'In Progress': 'success',
            'Overdue': 'danger',
            'Completed': 'secondary'
        }
        return status_colors.get(self.status, 'secondary')
    
    def check_overdue(self):
        """Check if task is overdue."""
        if self.status == 'Completed':
            return False
        if self.due_date and date.today() > self.due_date:
            self.status = 'Overdue'
            return True
        return False
    
    def __repr__(self):
        return f'<Task {self.content[:30]}...>'


# ============================================================================
# ACTIVITY LOG MODEL
# ============================================================================

class ActivityLog(db.Model):
    """Activity Log model for tracking user operations."""
    
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)  # Redundant for easy display
    action_type = db.Column(db.String(100), nullable=False)  # e.g., "Leads - Imported"
    subject_type = db.Column(db.String(50))  # lead, pipeline, task, account
    subject_id = db.Column(db.Integer, nullable=True)
    subject_name = db.Column(db.String(200))  # Name at time of action
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to User
    user = db.relationship('User', backref='activity_logs')
    
    def get_action_icon(self):
        """Return Bootstrap icon based on action type."""
        action_icons = {
            'Leads - Imported': 'bi-file-earmark-spreadsheet',
            'Leads - Created': 'bi-person-plus',
            'Leads - Updated': 'bi-person',
            'Leads - Deleted': 'bi-person-x',
            'Pipeline - Created': 'bi-graph-up',
            'Pipeline - Stage Changed': 'bi-arrow-left-right',
            'Pipeline - Updated': 'bi-graph-up',
            'Pipeline - Deleted': 'bi-trash',
            'Task - Created': 'bi-check-circle',
            'Task - Completed': 'bi-check-lg',
            'Task - Reopened': 'bi-arrow-counterclockwise',
            'Follow up - Note': 'bi-chat-text',
            'Account - Created': 'bi-building',
            'Account - Updated': 'bi-building',
        }
        return action_icons.get(self.action_type, 'bi-activity')
    
    def get_action_badge(self):
        """Return Bootstrap color class based on action type."""
        if 'Created' in self.action_type or 'Imported' in self.action_type:
            return 'success'
        elif 'Updated' in self.action_type or 'Changed' in self.action_type:
            return 'primary'
        elif 'Deleted' in self.action_type:
            return 'danger'
        elif 'Completed' in self.action_type:
            return 'success'
        else:
            return 'secondary'
    
    def __repr__(self):
        return f'<ActivityLog {self.action_type} by {self.user_name}>'


# ============================================================================
# WEEKLY METRICS MODEL
# ============================================================================

class WeeklyMetrics(db.Model):
    """
    周汇总表 - 存储按 owner + 周 汇总的指标
    
    核心逻辑：
    - 每次 Leads/Pipeline 变动时，自动更新该 owner 的本周汇总
    - 按 owner_id + week_start 唯一
    - owner_id = NULL 表示全公司汇总
    - Dashboard 直接查询，无需实时计算
    """
    
    __tablename__ = 'weekly_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, nullable=True)  # NULL = 全公司汇总
    week_start = db.Column(db.Date, nullable=False)  # 周一日期
    
    # 五大指标
    leads_count = db.Column(db.Integer, default=0)           # Leads 数量（不含 Unqualified）
    qualified_leads_count = db.Column(db.Integer, default=0)  # Qualified Leads 数量
    pipeline_count = db.Column(db.Integer, default=0)        # Pipeline 数量（不含 Deal Lost）
    tcv = db.Column(db.Integer, default=0)                  # TCV 总和（不含 Deal Lost）
    current_qtr_revenue = db.Column(db.Integer, default=0)  # 本季度收入
    next_qtr_revenue = db.Column(db.Integer, default=0)     # 下季度收入
    
    # 周环比（vs last week）
    leads_vs_last_week = db.Column(db.Integer, default=0)
    qualified_vs_last_week = db.Column(db.Integer, default=0)
    pipeline_vs_last_week = db.Column(db.Integer, default=0)
    tcv_vs_last_week = db.Column(db.Integer, default=0)
    
    # 月环比（vs last month）
    leads_vs_last_month = db.Column(db.Integer, default=0)
    qualified_vs_last_month = db.Column(db.Integer, default=0)
    pipeline_vs_last_month = db.Column(db.Integer, default=0)
    tcv_vs_last_month = db.Column(db.Integer, default=0)
    
    # 元数据
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('owner_id', 'week_start', name='uq_weekly_owner_week'),
    )
    
    def __repr__(self):
        return f'<WeeklyMetrics owner={self.owner_id} week={self.week_start}>'


# ============================================================================
# AUTO-UPDATE WEEKLY METRICS ON DATA CHANGES
# ============================================================================

from dateutil.relativedelta import relativedelta
import calendar
from sqlalchemy import event


def get_current_monday():
    """Get the Monday of the current week."""
    today = date.today()
    return today - relativedelta(days=today.weekday())


def get_last_monday():
    """Get the Monday of the last week."""
    this_monday = get_current_monday()
    return this_monday - relativedelta(weeks=1)


def get_current_month_start():
    """Get the first day of the current month."""
    today = date.today()
    return date(today.year, today.month, 1)


def get_last_month_start():
    """Get the first day of the last month."""
    current_month = get_current_month_start()
    return current_month - relativedelta(months=1)


def get_last_month_end():
    """Get the last day of the last month."""
    last_month = get_last_month_start()
    last_day = calendar.monthrange(last_month.year, last_month.month)[1]
    return date(last_month.year, last_month.month, last_day)


def get_quarter_dates(ref_date):
    """Get quarter start and end dates."""
    quarter_start_month = (ref_date.month - 1) // 3 * 3 + 1
    quarter_end_month = quarter_start_month + 2
    quarter_start = date(ref_date.year, quarter_start_month, 1)
    quarter_end = date(ref_date.year, quarter_end_month, 
                        calendar.monthrange(ref_date.year, quarter_end_month)[1])
    return quarter_start, quarter_end


def refresh_weekly_metrics_for_user(user_id, db_session):
    """
    Refresh WeeklyMetrics for a specific user and company.
    Uses PostgreSQL UPSERT (ON CONFLICT) for concurrent safety.
    """
    from models import WeeklyMetrics, SalesLead, Pipeline, User
    
    this_monday = get_current_monday()
    last_monday = get_last_monday()
    
    current_qtr_start, current_qtr_end = get_quarter_dates(date.today())
    
    # Calculate next quarter
    next_qtr_year = current_qtr_end.year
    next_qtr_month = current_qtr_end.month + 1
    if next_qtr_month > 12:
        next_qtr_year += 1
        next_qtr_month = 1
    next_qtr_start = date(next_qtr_year, next_qtr_month, 1)
    next_qtr_end = date(next_qtr_year, next_qtr_month, 
                        calendar.monthrange(next_qtr_year, next_qtr_month)[1])
    
    def calc_qtr_rev(pipelines, q_start, q_end):
        """Calculate quarter revenue for a list of pipelines."""
        total = 0
        for p in pipelines:
            if p.stage == '6b) Deal Lost':
                continue
            if not p.est_act_date:
                continue
            if p.est_act_date > q_end:
                continue
            
            otc = p.otc_usd or 0
            
            mrc = 0
            months = [(q_start.replace(day=28) + relativedelta(days=4)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=1)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=2)).replace(day=1)]
            
            for m_start in months:
                m_end = (m_start + relativedelta(months=1)) - relativedelta(days=1)
                if p.est_act_date > m_end:
                    continue
                elif p.est_act_date >= m_start and p.est_act_date <= m_end:
                    act_day = p.est_act_date.day
                    days_in_month = (m_end - m_start).days + 1
                    mrc += (p.mrc_usd or 0) * (act_day / days_in_month)
                else:
                    mrc += (p.mrc_usd or 0)
            
            total += int(otc + mrc)
        return total
    
    # Calculate current metrics for user
    user_pipelines = Pipeline.query.filter_by(owner_id=user_id).all()
    
    leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    qualified_leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    pipeline_count = len(user_pipelines)
    tcv = sum(p.tcv_usd or 0 for p in user_pipelines)
    current_qtr_revenue = calc_qtr_rev(user_pipelines, current_qtr_start, current_qtr_end)
    next_qtr_revenue = calc_qtr_rev(user_pipelines, next_qtr_start, next_qtr_end)
    
    # Get last week metrics for week-over-week comparison
    last_week_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_monday
    ).first()
    
    # Get last month metrics for month-over-month comparison
    # Find the Monday of the last month's first week
    last_month_start = get_current_month_start() - relativedelta(months=1)
    last_month_first_monday = last_month_start - relativedelta(days=last_month_start.weekday())
    last_month_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_month_first_monday
    ).first()
    
    # Calculate week-over-week changes
    leads_vs_last_week = leads_count - (last_week_metrics.leads_count if last_week_metrics else 0)
    qualified_vs_last_week = qualified_leads_count - (last_week_metrics.qualified_leads_count if last_week_metrics else 0)
    pipeline_vs_last_week = pipeline_count - (last_week_metrics.pipeline_count if last_week_metrics else 0)
    tcv_vs_last_week = tcv - (last_week_metrics.tcv if last_week_metrics else 0)
    
    # Calculate month-over-month changes (compare with last month's first week data)
    leads_vs_last_month = leads_count - (last_month_metrics.leads_count if last_month_metrics else 0)
    qualified_vs_last_month = qualified_leads_count - (last_month_metrics.qualified_leads_count if last_month_metrics else 0)
    pipeline_vs_last_month = pipeline_count - (last_month_metrics.pipeline_count if last_month_metrics else 0)
    tcv_vs_last_month = tcv - (last_month_metrics.tcv if last_month_metrics else 0)
    
    # UPSERT user metrics using PostgreSQL ON CONFLICT (atomic operation)
    upsert_sql = """
        INSERT INTO weekly_metrics (
            owner_id, week_start, leads_count, qualified_leads_count,
            pipeline_count, tcv, current_qtr_revenue, next_qtr_revenue,
            leads_vs_last_week, qualified_vs_last_week, pipeline_vs_last_week, tcv_vs_last_week,
            leads_vs_last_month, qualified_vs_last_month, pipeline_vs_last_month, tcv_vs_last_month,
            updated_at
        ) VALUES (
            :owner_id, :week_start, :leads_count, :qualified_leads_count,
            :pipeline_count, :tcv, :current_qtr_revenue, :next_qtr_revenue,
            :leads_vs_last_week, :qualified_vs_last_week, :pipeline_vs_last_week, :tcv_vs_last_week,
            :leads_vs_last_month, :qualified_vs_last_month, :pipeline_vs_last_month, :tcv_vs_last_month,
            NOW()
        )
        ON CONFLICT (owner_id, week_start) DO UPDATE SET
            leads_count = EXCLUDED.leads_count,
            qualified_leads_count = EXCLUDED.qualified_leads_count,
            pipeline_count = EXCLUDED.pipeline_count,
            tcv = EXCLUDED.tcv,
            current_qtr_revenue = EXCLUDED.current_qtr_revenue,
            next_qtr_revenue = EXCLUDED.next_qtr_revenue,
            leads_vs_last_week = EXCLUDED.leads_vs_last_week,
            qualified_vs_last_week = EXCLUDED.qualified_vs_last_week,
            pipeline_vs_last_week = EXCLUDED.pipeline_vs_last_week,
            tcv_vs_last_week = EXCLUDED.tcv_vs_last_week,
            leads_vs_last_month = EXCLUDED.leads_vs_last_month,
            qualified_vs_last_month = EXCLUDED.qualified_vs_last_month,
            pipeline_vs_last_month = EXCLUDED.pipeline_vs_last_month,
            tcv_vs_last_month = EXCLUDED.tcv_vs_last_month,
            updated_at = NOW()
    """
    
    db_session.execute(db.text(upsert_sql), {
        'owner_id': user_id,
        'week_start': this_monday,
        'leads_count': leads_count,
        'qualified_leads_count': qualified_leads_count,
        'pipeline_count': pipeline_count,
        'tcv': int(tcv),
        'current_qtr_revenue': current_qtr_revenue,
        'next_qtr_revenue': next_qtr_revenue,
        'leads_vs_last_week': leads_vs_last_week,
        'qualified_vs_last_week': qualified_vs_last_week,
        'pipeline_vs_last_week': pipeline_vs_last_week,
        'tcv_vs_last_week': int(tcv_vs_last_week),
        'leads_vs_last_month': leads_vs_last_month,
        'qualified_vs_last_month': qualified_vs_last_month,
        'pipeline_vs_last_month': pipeline_vs_last_month,
        'tcv_vs_last_month': int(tcv_vs_last_month),
    })
    
    # Also refresh company-wide metrics (owner_id = NULL)
    all_pipelines = Pipeline.query.all()
    
    company_leads_count = SalesLead.query.filter(
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    company_qualified_leads_count = SalesLead.query.filter(
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    company_pipeline_count = len([p for p in all_pipelines if p.stage != '6b) Deal Lost'])
    company_tcv = sum(p.tcv_usd or 0 for p in all_pipelines if p.stage != '6b) Deal Lost')
    company_current_qtr = calc_qtr_rev(all_pipelines, current_qtr_start, current_qtr_end)
    company_next_qtr = calc_qtr_rev(all_pipelines, next_qtr_start, next_qtr_end)
    
    # Company week-over-week comparison
    company_last_week = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_monday
    ).first()
    
    # Company month-over-month comparison
    company_last_month = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_month_first_monday
    ).first()
    
    company_leads_vs_last_week = company_leads_count - (company_last_week.leads_count if company_last_week else 0)
    company_qualified_vs_last_week = company_qualified_leads_count - (company_last_week.qualified_leads_count if company_last_week else 0)
    company_pipeline_vs_last_week = company_pipeline_count - (company_last_week.pipeline_count if company_last_week else 0)
    company_tcv_vs_last_week = company_tcv - (company_last_week.tcv if company_last_week else 0)
    
    company_leads_vs_last_month = company_leads_count - (company_last_month.leads_count if company_last_month else 0)
    company_qualified_vs_last_month = company_qualified_leads_count - (company_last_month.qualified_leads_count if company_last_month else 0)
    company_pipeline_vs_last_month = company_pipeline_count - (company_last_month.pipeline_count if company_last_month else 0)
    company_tcv_vs_last_month = company_tcv - (company_last_month.tcv if company_last_month else 0)
    
    # UPSERT company metrics (owner_id = NULL)
    db_session.execute(db.text(upsert_sql), {
        'owner_id': None,
        'week_start': this_monday,
        'leads_count': company_leads_count,
        'qualified_leads_count': company_qualified_leads_count,
        'pipeline_count': company_pipeline_count,
        'tcv': int(company_tcv),
        'current_qtr_revenue': company_current_qtr,
        'next_qtr_revenue': company_next_qtr,
        'leads_vs_last_week': company_leads_vs_last_week,
        'qualified_vs_last_week': company_qualified_vs_last_week,
        'pipeline_vs_last_week': company_pipeline_vs_last_week,
        'tcv_vs_last_week': int(company_tcv_vs_last_week),
        'leads_vs_last_month': company_leads_vs_last_month,
        'qualified_vs_last_month': company_qualified_vs_last_month,
        'pipeline_vs_last_month': company_pipeline_vs_last_month,
        'tcv_vs_last_month': int(company_tcv_vs_last_month),
    })


# ============================================================================
# SQLALCHEMY EVENT LISTENERS FOR AUTO-UPDATE
# ============================================================================

# Flag to temporarily disable event listeners during bulk operations
_disable_metrics_events = False


@event.listens_for(SalesLead, 'after_insert')
@event.listens_for(SalesLead, 'after_update')
@event.listens_for(SalesLead, 'after_delete')
def on_lead_change(mapper, connection, target):
    """Auto-refresh WeeklyMetrics when a Lead is changed."""
    global _disable_metrics_events
    if target.owner_id and not _disable_metrics_events:
        try:
            refresh_weekly_metrics_for_user(target.owner_id, db.session)
        except Exception:
            pass  # Ignore errors (e.g., concurrent updates)


@event.listens_for(Pipeline, 'after_insert')
@event.listens_for(Pipeline, 'after_update')
@event.listens_for(Pipeline, 'after_delete')
def on_pipeline_change(mapper, connection, target):
    """Auto-refresh WeeklyMetrics when a Pipeline is changed."""
    global _disable_metrics_events
    if target.owner_id and not _disable_metrics_events:
        try:
            refresh_weekly_metrics_for_user(target.owner_id, db.session)
        except Exception:
            pass  # Ignore errors (e.g., concurrent updates)


@contextmanager
def disable_metrics_events():
    """Context manager to temporarily disable metrics events."""
    global _disable_metrics_events
    _disable_metrics_events = True
    try:
        yield
    finally:
        _disable_metrics_events = False
