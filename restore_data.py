import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')
from app import create_app
from extensions import db
from models import SalesLead, Pipeline, WeeklyMetrics
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import random

app = create_app()
with app.app_context():
    print("检查数据状态...")
    leads_count = SalesLead.query.count()
    pipeline_count = Pipeline.query.count()
    print(f"Leads: {leads_count}")
    print(f"Pipeline: {pipeline_count}")
    
    if leads_count == 0:
        print("\n正在创建测试数据...")
        
        # 创建测试 Leads
        statuses = ['Qualified', 'Waiting for Response', 'Unqualified', 'Waiting to be Contacted']
        
        for i in range(100):
            lead = SalesLead(
                name=f'Test Lead {i+1}',
                company=f'Company {i+1}',
                email=f'contact{i+1}@company{i+1}.com',
                mobile_number=f'+123456789{i}',
                owner_id=random.randint(1, 15),
                leads_status=random.choice(statuses),
                source='Website',
                created_at=datetime.now(),
                date_added=date.today()
            )
            db.session.add(lead)
        
        db.session.commit()
        print(f"创建了 {SalesLead.query.count()} 条 Leads")
    
    if pipeline_count == 0:
        print("\n正在创建测试 Pipeline...")
        
        stages = ['1) Prospecting', '2) Lead Qualified', '3) Demo/Meeting', 
                  '4) Proposal Submitted', '5) Negotiation', '6a) Deal Won', '7) Activated']
        levels = ['Stretch', 'Expected', 'Committed']
        
        for i in range(50):
            pipeline = Pipeline(
                name=f'Pipeline Deal {i+1}',
                company=f'Client Company {i+1}',
                product=f'Product {random.randint(1, 5)}',
                owner_id=random.randint(1, 15),
                stage=random.choice(stages),
                level=random.choice(levels),
                tcv_usd=random.randint(50000, 500000),
                mrc_usd=random.randint(5000, 50000),
                otc_usd=random.randint(10000, 100000),
                est_sign_date=date.today() + relativedelta(days=random.randint(30, 180)),
                win_rate=random.randint(20, 90) / 100,
                date_added=date.today()
            )
            db.session.add(pipeline)
        
        db.session.commit()
        print(f"创建了 {Pipeline.query.count()} 条 Pipeline")
    
    # 运行 metrics 更新
    print("\n运行 metrics 更新...")
    from models import refresh_weekly_metrics_for_user, get_current_monday
    from models import WeeklyMetrics
    
    # 清除旧的 metrics
    WeeklyMetrics.query.delete()
    db.session.commit()
    
    # 重新计算所有用户的 metrics
    from models import User
    users = User.query.filter_by(is_active=True).all()
    for user in users:
        refresh_weekly_metrics_for_user(user.id, db.session)
        print(f"  Updated: {user.username}")
    
    db.session.commit()
    print("\n完成！")
