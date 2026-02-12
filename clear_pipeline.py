import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')
from app import create_app
from models import Pipeline
from extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    count = Pipeline.query.count()
    print(f'当前 Pipeline 数据: {count} 条')
    
    if count > 0:
        Pipeline.query.delete()
        db.session.commit()
        print(f'已删除所有 Pipeline 数据')
        
        # 重置 ID
        db.session.execute(text("DELETE FROM sqlite_sequence WHERE name='pipeline'"))
        db.session.commit()
        print('ID 计数器已重置')
