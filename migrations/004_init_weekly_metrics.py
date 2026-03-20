#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移脚本：初始化 weekly_metrics 表
"""
from __future__ import print_function

import sys
import os

# 确保当前目录在路径中
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app import create_app
from models import WeeklyMetrics, User, Pipeline, SalesLead
from utils import calculate_quarter_revenue, get_current_quarter_dates, get_next_quarter_dates
from extensions import db
from datetime import date, timedelta


def get_week_start(ref_date=None):
    """获取本周一日期"""
    if ref_date is None:
        ref_date = date.today()
    return ref_date - timedelta(days=ref_date.weekday())


def init_weekly_metrics():
    """初始化 weekly_metrics 表"""
    app = create_app()
    
    with app.app_context():
        today = date.today()
        week_start = get_week_start(today)
        quarter_start, quarter_end = get_current_quarter_dates(today)
        next_qtr_start, next_qtr_end = get_next_quarter_dates(today)

        print('=' * 50)
        print('初始化 Weekly Metrics 数据')
        print('=' * 50)

        # 全公司汇总
        all_pipelines = Pipeline.query.filter(
            Pipeline.stage != '6b) Deal Lost'
        ).all()
        all_leads = SalesLead.query.filter(
            SalesLead.leads_status != 'Unqualified'
        ).all()
        
        leads_count = len(all_leads)
        qualified_leads_count = SalesLead.query.filter(
            SalesLead.leads_status == 'Qualified'
        ).count()
        pipeline_count = len(all_pipelines)
        tcv = sum(p.tcv_usd or 0 for p in all_pipelines)
        current_qtr_rev = calculate_quarter_revenue(all_pipelines, quarter_start, quarter_end)
        next_qtr_rev = calculate_quarter_revenue(all_pipelines, next_qtr_start, next_qtr_end)

        existing = WeeklyMetrics.query.filter_by(owner_id=None, week_start=week_start).first()
        if existing:
            existing.leads_count = leads_count
            existing.qualified_leads_count = qualified_leads_count
            existing.pipeline_count = pipeline_count
            existing.tcv = tcv
            existing.current_qtr_revenue = current_qtr_rev
            existing.next_qtr_revenue = next_qtr_rev
            print('更新全公司汇总')
        else:
            record = WeeklyMetrics(
                owner_id=None, 
                week_start=week_start,
                leads_count=leads_count, 
                qualified_leads_count=qualified_leads_count,
                pipeline_count=pipeline_count, 
                tcv=tcv,
                current_qtr_revenue=current_qtr_rev, 
                next_qtr_revenue=next_qtr_rev
            )
            db.session.add(record)
            print('创建全公司汇总')
        
        db.session.commit()
        print('全公司: leads=%d, pipeline=%d, tcv=%d' % (leads_count, pipeline_count, tcv))

        # 用户汇总
        users = User.query.filter_by(is_active=True).all()
        for user in users:
            user_pipelines = Pipeline.query.filter(
                Pipeline.owner_id == user.id, 
                Pipeline.stage != '6b) Deal Lost'
            ).all()
            user_leads = SalesLead.query.filter(
                SalesLead.owner_id == user.id, 
                SalesLead.leads_status != 'Unqualified'
            ).count()
            user_qualified = SalesLead.query.filter(
                SalesLead.owner_id == user.id, 
                SalesLead.leads_status == 'Qualified'
            ).count()
            
            user_pipeline_count = len(user_pipelines)
            user_tcv = sum(p.tcv_usd or 0 for p in user_pipelines)
            user_current_qtr = calculate_quarter_revenue(user_pipelines, quarter_start, quarter_end)
            user_next_qtr = calculate_quarter_revenue(user_pipelines, next_qtr_start, next_qtr_end)

            existing = WeeklyMetrics.query.filter_by(owner_id=user.id, week_start=week_start).first()
            if existing:
                existing.leads_count = user_leads
                existing.qualified_leads_count = user_qualified
                existing.pipeline_count = user_pipeline_count
                existing.tcv = user_tcv
                existing.current_qtr_revenue = user_current_qtr
                existing.next_qtr_revenue = user_next_qtr
            else:
                record = WeeklyMetrics(
                    owner_id=user.id, 
                    week_start=week_start,
                    leads_count=user_leads, 
                    qualified_leads_count=user_qualified,
                    pipeline_count=user_pipeline_count, 
                    tcv=user_tcv,
                    current_qtr_revenue=user_current_qtr, 
                    next_qtr_revenue=user_next_qtr
                )
                db.session.add(record)
            
            print('%s: leads=%d, qualified=%d, pipeline=%d, tcv=%d' % (
                user.username, user_leads, user_qualified, user_pipeline_count, user_tcv))
        
        db.session.commit()
        print('=' * 50)
        print('初始化完成！')
        print('=' * 50)


if __name__ == '__main__':
    init_weekly_metrics()
