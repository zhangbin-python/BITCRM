"""
BITCRM Utility Functions
Helper functions for Excel import/export, calculations, and date utilities.
"""
import pandas as pd
import openpyxl
from datetime import datetime, date
from flask import flash
from io import BytesIO
from dateutil import parser
import os


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}


def validate_date(date_str):
    """Validate and parse date string."""
    if not date_str:
        return None
    
    # Handle date/datetime objects (already parsed)
    if hasattr(date_str, 'strftime') and not isinstance(date_str, str):
        # Already a date/datetime object - return as-is
        return date_str if isinstance(date_str, date) else date_str.date()
    
    # Handle numeric Excel date values (serial numbers like 44927)
    if isinstance(date_str, (int, float)):
        # Convert Excel serial date to date object
        result = excel_date_to_date(date_str)
        if result:
            return result
        return None
    
    # Must be string at this point
    if not isinstance(date_str, str):
        return None
    
    date_str_clean = date_str.strip()
    
    # Extended date formats list
    date_formats = [
        # 标准格式
        '%Y-%m-%d',           # 2024-01-01
        '%Y/%m/%d',           # 2024/01/01
        '%Y.%m.%d',           # 2024.01.01
        
        # 中文格式
        '%Y年%m月%d日',       # 2024年01月01日
        '%Y年%m月%d日',       # 2024年1月1日
        '%m月%d日',           # 01月01日 或 1月1日
        
        # 美式格式
        '%m/%d/%Y',           # 01/01/2024
        '%m-%d-%Y',           # 01-01-2024
        '%m.%d.%Y',           # 01.01.2024
        
        # 英式格式
        '%d/%m/%Y',           # 01/01/2024
        '%d-%m-%Y',           # 01-01-2024
        '%d.%m.%Y',           # 01.01.2024
        
        # 英文全称格式
        '%B %d, %Y',          # January 1, 2024
        '%b %d, %Y',          # Jan 1, 2024
        '%d %B %Y',           # 1 January 2024
        '%d %b %Y',           # 1 Jan 2024
        
        # 短格式
        '%Y%m%d',             # 20240101
        '%y-%m-%d',           # 24-01-01
        '%y/%m/%d',           # 24/01/01
        
        # 带时区的ISO格式
        '%Y-%m-%dT%H:%M:%S', # 2024-01-01T00:00:00
        '%Y-%m-%d %H:%M:%S',  # 2024-01-01 00:00:00
    ]
    
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(date_str_clean, fmt).date()
            return parsed
        except ValueError:
            continue
    
    # Try dateutil parser as fallback (handles many edge cases)
    try:
        parsed = parser.parse(date_str_clean).date()
        return parsed
    except:
        return None


def validate_email(email):
    """Basic email validation."""
    if not email:
        return True  # Empty is valid (optional field)
    import re
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))


def validate_numeric(value, field_name):
    """Validate and convert numeric value."""
    if value is None or value == '':
        return 0
    try:
        # Remove commas and spaces
        cleaned = str(value).replace(',', '').replace(' ', '')
        return int(float(cleaned))
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number")


def create_excel_template(columns, filename):
    """Create an Excel template file."""
    df = pd.DataFrame(columns=columns)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    
    output.seek(0)
    return output


def export_to_excel(data, columns, filename):
    """Export data to Excel file."""
    if not data:
        df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(data, columns=columns)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    
    output.seek(0)
    return output


def import_from_excel(file_stream):
    """Import data from Excel file."""
    try:
        # Read Excel, keeping dates as-is (they may be datetime objects or numbers)
        df = pd.read_excel(file_stream)
        # Clean column names
        df.columns = df.columns.str.strip()
        # Replace NaN with None
        df = df.where(pd.notnull(df), None)
        return df
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {str(e)}")


def excel_date_to_str(val):
    """Convert Excel date (numeric or datetime) to string format YYYY-MM-DD."""
    if val is None:
        return None
    
    # Already a datetime
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    
    # Excel date serial number (Windows: 1900-based, Mac: 1904-based)
    try:
        # Try to convert numeric Excel date
        val_float = float(val)
        # Excel epoch is 1900-01-01 (Windows) or 1904-01-01 (Mac)
        # Most common: Windows Excel (1900 epoch)
        # Excel has a bug where 1900-02-29 is treated as valid, so we handle that
        if val_float >= 60:  # After 1900-02-28
            # Windows Excel (1900 epoch)
            dt = datetime(1899, 12, 30) + timedelta(days=int(val_float))
        else:
            # Before 1900-02-28 - could be Mac Excel (1904 epoch)
            # Try 1904 epoch
            dt = datetime(1904, 1, 1) + timedelta(days=int(val_float))
            if dt.year < 1900:
                # Fallback to 1900 epoch
                dt = datetime(1899, 12, 30) + timedelta(days=int(val_float))
        return dt.strftime('%Y-%m-%d')
    except:
        return None


def excel_date_to_date(val):
    """Convert Excel date (numeric or datetime) to Python date object."""
    result = excel_date_to_str(val)
    if result:
        return datetime.strptime(result, '%Y-%m-%d').date()
    return None


def validate_sales_lead_import(row):
    """Validate a single sales lead import row."""
    errors = []
    
    # Required fields (key is already normalized to lowercase with underscores)
    if not row.get('name'):
        errors.append("Name is required")
    
    # Validate status - 支持大小写不敏感匹配
    valid_statuses_lower = {
        'qualified': 'Qualified',
        'waiting for response': 'Waiting for Response',
        'unqualified': 'Unqualified',
        'waiting to be contacted': 'Waiting to be Contacted'
    }
    status = row.get('leads_status', '')
    # Ensure status is a string for comparison
    if status and not isinstance(status, str):
        status = str(status)
    if status:
        status_lower = status.strip().lower()
        if status_lower in valid_statuses_lower:
            # 自动转换为正确的格式
            row['leads_status'] = valid_statuses_lower[status_lower]
        else:
            errors.append(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses_lower.values())}")
    
    # Validate source - 支持大小写不敏感匹配，处理多值情况
    valid_sources_lower = {
        'website': 'Website',
        'referral': 'Referral',
        'email campaign': 'Email Campaign',
        'social media': 'Social Media',
        'event': 'Event',
        'trade show': 'Trade Show',
        'advertisement': 'Advertisement',
        'partner': 'Partner',
        'direct inquiry': 'Direct Inquiry'
    }
    source = row.get('source', '')
    if source and not isinstance(source, str):
        source = str(source)
    if source:
        source_clean = source.strip()
        source_lower = source_clean.lower()
        
        # 检查是否包含斜杠的多值情况（如 'Event/Trade Show'）
        if '/' in source_clean:
            # 取第一个值
            first_source = source_clean.split('/')[0].strip()
            first_source_lower = first_source.lower()
            if first_source_lower in valid_sources_lower:
                row['source'] = valid_sources_lower[first_source_lower]
            else:
                errors.append(f"Invalid source '{source}'. Must be one of: {', '.join(valid_sources_lower.values())}")
        elif source_lower in valid_sources_lower:
            # 自动转换为正确的格式
            row['source'] = valid_sources_lower[source_lower]
        else:
            errors.append(f"Invalid source '{source}'. Must be one of: {', '.join(valid_sources_lower.values())}")
    
    # Validate date
    if row.get('date_added'):
        date_val = validate_date(row.get('date_added'))
        if not date_val:
            errors.append(f"Invalid date format '{row.get('date_added')}'. Supported formats: YYYY-MM-DD (2025-03-28), YYYY/MM/DD, Jan 1, 2024, etc.")
        else:
            row['date_added'] = date_val
    
    # Validate email
    if row.get('email') and not validate_email(row.get('email')):
        errors.append(f"Invalid email format '{row.get('email')}'")
    
    return errors


def validate_pipeline_import(row):
    """Validate a single pipeline import row."""
    errors = []
    
    # Name is optional
    # if not row.get('Name'):
    #     errors.append("Name is required")
    
    # Validate stage
    valid_stages = ['1) Prospecting', '2) Lead Qualified', '3) Demo/Meeting',
                    '4) Proposal Submitted', '5) Negotiation', '6a) Deal Won',
                    '6b) Deal Lost', '7) Activated']
    stage = row.get('Stage', '')
    # Ensure stage is a string for comparison
    if stage and not isinstance(stage, str):
        stage = str(stage)
    if stage and stage not in valid_stages:
        errors.append(f"Invalid stage '{stage}'. Must be one of: {', '.join(valid_stages)}")
    
    # Validate level
    valid_levels = ['Committed', 'Stretch']
    level = row.get('Level', '')
    # Ensure level is a string for comparison
    if level and not isinstance(level, str):
        level = str(level)
    if level and level not in valid_levels:
        errors.append(f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}")
    
    # Validate dates
    for date_field in ['Est. Sign Date', 'Est. Act. Date', 'Award Date', 'Proposal Sent Date']:
        if row.get(date_field):
            date_val = validate_date(row.get(date_field))
            if not date_val:
                errors.append(f"Invalid date format '{row.get(date_field)}' for {date_field}")
            else:
                row[date_field] = date_val
    
    # Validate numeric fields
    numeric_fields = ['TCV USD', 'MRC USD', 'OTC USD', 'Contract Term (Yrs)', 
                      'GP Margin', 'Win Rate']
    for field in numeric_fields:
        if row.get(field) and field in ['TCV USD', 'MRC USD', 'OTC USD', 'Contract Term (Yrs)']:
            try:
                val = validate_numeric(row.get(field), field)
                row[field] = val
            except ValueError as e:
                errors.append(str(e))
    
    # Validate GP Margin (percentage)
    if row.get('GP Margin'):
        try:
            margin = float(str(row.get('GP Margin')).replace('%', '').replace(',', ''))
            if margin < 0 or margin > 1:
                errors.append("GP Margin must be between 0 and 1 (or 0% to 100%)")
            else:
                row['GP Margin'] = margin
        except ValueError:
            errors.append("GP Margin must be a valid number")
    
    # Validate Win Rate (percentage, 5% multiples)
    if row.get('Win Rate'):
        try:
            win_rate = float(str(row.get('Win Rate')).replace('%', '').replace(',', ''))
            if win_rate < 0 or win_rate > 100:
                errors.append("Win Rate must be between 0 and 100")
            elif win_rate % 5 != 0:
                errors.append("Win Rate must be in 5% multiples (0, 5, 10, ..., 100)")
            else:
                row['Win Rate'] = win_rate / 100
        except ValueError:
            errors.append("Win Rate must be a valid number")
    
    return errors


def calculate_pipeline_metrics(pipeline):
    """Calculate and update pipeline metrics."""
    # Calculate TCV (4 decimal places)
    pipeline.tcv_usd = round((pipeline.mrc_usd * 12 * pipeline.contract_term_yrs) + pipeline.otc_usd, 4)
    
    # Calculate ACV (Annual Contract Value)
    acv = pipeline.mrc_usd * 12
    
    # Calculate GP (4 decimal places)
    pipeline.gp = round(pipeline.tcv_usd * pipeline.gp_margin, 4)
    
    # Determine MG (Margin Grade)
    if pipeline.gp_margin >= 0.5:
        pipeline.mg = 'A'
    elif pipeline.gp_margin >= 0.35:
        pipeline.mg = 'B'
    elif pipeline.gp_margin >= 0.2:
        pipeline.mg = 'C'
    else:
        pipeline.mg = 'D'
    
    return pipeline


def format_currency(value):
    """Format number as USD currency."""
    return f"${value:,}"


def format_currency_thousands(value):
    """Format number as USD currency with thousands separator, no decimals."""
    if value is None:
        return '$0'
    return f"${int(value):,}"


def format_currency_short(value):
    """Format number as USD currency in short format (e.g., $1.5M, $150K)."""
    if value is None:
        return '$0'
    if value >= 1000000:
        return f"${value / 1000000:.2f}M"
    elif value >= 1000:
        return f"${int(value / 1000)}K"
    else:
        return f"${int(value)}"


def format_vs_indicator(value, inverse=False):
    """Format vs indicator with color and arrow."""
    if value is None:
        return {'text': '-', 'class': 'text-muted', 'icon': ''}
    if value > 0:
        return {'text': f'+{value}', 'class': 'text-success', 'icon': '↑'}
    elif value < 0:
        return {'text': str(value), 'class': 'text-danger', 'icon': '↓'}
    else:
        return {'text': '0', 'class': 'text-muted', 'icon': '-'}


def get_week_of_year(date_obj=None):
    """Get ISO week number and year."""
    if not date_obj:
        date_obj = date.today()
    return date_obj.isocalendar()[1], date_obj.year


def calculate_weekly_growth(current_value, previous_value):
    """Calculate percentage growth between two values."""
    if previous_value == 0:
        return 100.0 if current_value > 0 else 0.0
    return ((current_value - previous_value) / previous_value) * 100


def get_previous_week_range(reference_date=None):
    """Get the date range for the previous week."""
    if not reference_date:
        reference_date = date.today()
    
    # Get to the start of this week (Monday)
    days_since_monday = reference_date.weekday()
    this_monday = reference_date - timedelta(days=days_since_monday)
    
    # Previous week's Monday and Sunday
    prev_monday = this_monday - timedelta(days=7)
    prev_sunday = this_monday - timedelta(days=1)
    
    return prev_monday, prev_sunday


def get_this_week_range(reference_date=None):
    """Get the date range for this week."""
    if not reference_date:
        reference_date = date.today()
    
    days_since_monday = reference_date.weekday()
    this_monday = reference_date - timedelta(days=days_since_monday)
    this_sunday = this_monday + timedelta(days=6)
    
    return this_monday, this_sunday


from datetime import timedelta
from dateutil.relativedelta import relativedelta
import calendar


def get_quarter_dates(reference_date=None):
    """
    Get the start and end dates of the current quarter.
    Returns (quarter_start, quarter_end) as date objects.
    """
    if not reference_date:
        reference_date = date.today()
    
    quarter_start_month = (reference_date.month - 1) // 3 * 3 + 1
    quarter_end_month = quarter_start_month + 2
    
    quarter_start = date(reference_date.year, quarter_start_month, 1)
    quarter_end = date(reference_date.year, quarter_end_month, 
                        calendar.monthrange(reference_date.year, quarter_end_month)[1])
    
    return quarter_start, quarter_end


# Alias for compatibility
get_current_quarter_dates = get_quarter_dates


def get_next_quarter_dates(reference_date=None):
    """
    Get the start and end dates of the next quarter.
    Returns (next_quarter_start, next_quarter_end) as date objects.
    """
    if not reference_date:
        reference_date = date.today()
    
    # Calculate next quarter
    next_quarter_month = ((reference_date.month - 1) // 3 + 1) * 3 + 1
    next_quarter_year = reference_date.year
    
    if next_quarter_month > 12:
        next_quarter_month -= 12
        next_quarter_year += 1
    
    next_quarter_start = date(next_quarter_year, next_quarter_month, 1)
    next_quarter_end = date(next_quarter_year, next_quarter_month + 2,
                             calendar.monthrange(next_quarter_year, next_quarter_month + 2)[1])
    
    return next_quarter_start, next_quarter_end


def get_months_between(start_date, end_date):
    """
    Get a list of (month_start, month_end) tuples between two dates.
    """
    months = []
    current = start_date
    
    while current <= end_date:
        month_start = date(current.year, current.month, 1)
        month_end = date(current.year, current.month,
                         calendar.monthrange(current.year, current.month)[1])
        months.append((month_start, month_end))
        current = month_end + timedelta(days=1)
    
    return months


def calculate_quarter_revenue(pipelines, quarter_start, quarter_end):
    """
    计算指定季度的收入
    
    核心逻辑：
    - 只统计 stage != '6b) Deal Lost' 的 Pipeline
    - OTC: 只有 activation_date 落在季度内才累加一次
    - MRC: 按月分摊计算
    
    Args:
        pipelines: Pipeline 对象列表
        quarter_start: 季度开始日期
        quarter_end: 季度结束日期
    
    Returns:
        int: 季度总收入（整数）
    """
    import calendar
    
    total_otc = 0
    total_mrc = 0
    
    for p in pipelines:
        # 跳过 Deal Lost
        if p.stage == '6b) Deal Lost':
            continue
        
        # OTC 计算：activation_date 落在季度内才累加
        if p.est_act_date and quarter_start <= p.est_act_date <= quarter_end:
            total_otc += p.otc_usd or 0
        
        # MRC 计算：按月分摊
        if not p.est_act_date:
            continue
        
        mrc = p.mrc_usd or 0
        if mrc == 0:
            continue
        
        # 遍历季度的3个月
        current_month = quarter_start
        while current_month <= quarter_end:
            month_start = date(current_month.year, current_month.month, 1)
            month_end = date(
                current_month.year,
                current_month.month,
                calendar.monthrange(current_month.year, current_month.month)[1]
            )
            
            if p.est_act_date < month_start:
                # 激活日期在月初之前：当月全额确认
                total_mrc += mrc
            elif month_start <= p.est_act_date <= month_end:
                # 激活日期在该月内：按比例确认
                days_in_month = (month_end - month_start).days + 1
                activated_days = month_end.day - p.est_act_date.day + 1
                total_mrc += mrc * (activated_days / days_in_month)
            # 激活日期在月之后：当月确认 0（不处理）
            
            current_month = month_end + timedelta(days=1)
    
    return int(total_otc + total_mrc)
