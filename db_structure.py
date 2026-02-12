"""
数据库结构查询脚本
用法: python db_structure.py
"""
import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')

from app import create_app
from extensions import db
from models import *

app = create_app()

with app.app_context():
    print("=" * 60)
    print("数据库结构概览")
    print("=" * 60)
    
    # 获取所有表名
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    
    print(f"\n📊 总表数: {len(tables)}")
    print("-" * 60)
    
    for table in tables:
        print(f"\n📌 表: {table}")
        print("-" * 40)
        
        # 获取列信息
        columns = inspector.get_columns(table)
        print(f"   列数: {len(columns)}")
        print(f"   列名:")
        
        for col in columns:
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            default = f" DEFAULT {col['default']}" if col['default'] else ""
            print(f"      {col['name']:30} {col['type']:20} {nullable}{default}")
        
        # 获取外键
        foreign_keys = inspector.get_foreign_keys(table)
        if foreign_keys:
            print(f"   外键:")
            for fk in foreign_keys:
                print(f"      {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
        
        # 获取索引
        indexes = inspector.get_indexes(table)
        if indexes:
            print(f"   索引:")
            for idx in indexes:
                unique = "UNIQUE" if idx['unique'] else ""
                print(f"      {idx['name']}: {idx['column_names']} {unique}")
    
    print("\n" + "=" * 60)
    print("模型类定义")
    print("=" * 60)
    
    # 列出所有模型类
    models = [
        User, Company, SalesLead, Pipeline, Activity,
        WeeklyMetrics, MonthlyRevenue, UserActivityLog,
        PipelineHistory
    ]
    
    for model in models:
        if hasattr(model, '__tablename__'):
            print(f"📌 {model.__name__} -> {model.__tablename__}")

if __name__ == '__main__':
    # 需要设置环境变量 DATABASE_URL
    import os
    if not os.environ.get('DATABASE_URL'):
        print("⚠️ 请设置 DATABASE_URL 环境变量:")
        print("   export DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
        print("   或")
        print("   $env:DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
