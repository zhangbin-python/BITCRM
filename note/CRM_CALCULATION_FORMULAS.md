# CRM 系统计算公式文档

> 最后更新: 2026-02-09
> 文档版本: 1.0

---

## 目录

1. [Pipeline 相关计算](#1-pipeline-相关计算)
2. [季度收入计算](#2-季度收入计算)
3. [周汇总计算](#3-周汇总计算)
4. [格式化函数](#4-格式化函数)
5. [日期计算](#5-日期计算)

---

## 1. Pipeline 相关计算

### 1.1 TCV (Total Contract Value) - 总合同价值

```python
def get_tcv(self):
    """Calculate Total Contract Value."""
    return (self.mrc_usd * 12 * self.contract_term_yrs) + self.otc_usd
```

**公式**:
```
TCV = MRC × 12 × 合同年限 + OTC
```

**示例**:
- MRC = $1,000/月
- OTC = $5,000
- 合同年限 = 3年
- TCV = $1,000 × 12 × 3 + $5,000 = $41,000

---

### 1.2 ACV (Annual Contract Value) - 年度合同价值

```python
def get_acv(self):
    """Calculate Annual Contract Value."""
    return self.mrc_usd * 12
```

**公式**:
```
ACV = MRC × 12
```

---

### 1.3 GP (Gross Profit) - 毛利

```python
def get_gp(self):
    """Calculate Gross Profit."""
    return int(self.tcv_usd * self.gp_margin)
```

**公式**:
```
GP = TCV × 毛利率
```

---

### 1.4 Pipeline Stage 状态选项

```python
STAGE_OPTIONS = [
    '1) Prospecting',      # 初步接触
    '2) Lead Qualified',  # 线索合格
    '3) Demo/Meeting',   # 演示/会议
    '4) Proposal Submitted',  # 提案已提交
    '5) Negotiation',     # 谈判中
    '6a) Deal Won',      # 赢单
    '6b) Deal Lost',     # 输单
    '7) Activated'       # 已激活
]
```

---

## 2. 季度收入计算

### 2.1 OTC (一次性收入) 计算

```python
def calculate_otc(pipeline, quarter_start, quarter_end):
    """
    OTC 只在 activation_date 落在对应季度内时，累加一次
    """
    if pipeline.est_act_date and quarter_start <= pipeline.est_act_date <= quarter_end:
        return pipeline.otc_usd or 0
    return 0
```

**规则**:
```
如果 activation_date 落在本季度内 → OTC 全额计入
如果 activation_date 在本季度外 → OTC 不计入
```

---

### 2.2 MRC (月度经常性收入) 按月分摊计算

```python
def calculate_mrc(pipeline, quarter_start, quarter_end):
    """
    对于季度内每个月：
    - activation_date < 月初：确认 100% MRC
    - activation_date 在该月内：(月底 - 激活日 + 1) / 当月天数 × MRC
    - activation_date > 月底：确认 0
    """
```

**公式**:
```
当月 MRC = MRC × (激活天数 / 当月天数)

其中：
激活天数 = 月底日期 - 激活日期 + 1
```

---

### 2.3 季度收入汇总

```python
def calculate_quarter_revenue(pipelines, quarter_start, quarter_end):
    """
    季度收入 = OTC + MRC
    
    只统计 stage != '6b) Deal Lost' 的 Pipeline
    """
    total_otc = 0
    total_mrc = 0
    
    for p in pipelines:
        if p.stage == '6b) Deal Lost':
            continue
        total_otc += calculate_otc(p, quarter_start, quarter_end)
        total_mrc += calculate_mrc(p, quarter_start, quarter_end)
    
    return int(total_otc + total_mrc)
```

**计算示例**:

假设 Pipeline A:
- MRC = $1,000/月
- OTC = $5,000
- activation_date = 2月15日
- 本季度 = Q1 (1-3月)

| 月份 | 激活日期 | 计算 | MRC |
|------|----------|------|-----|
| 1月 | - | 0 | $0 |
| 2月 | 2月15日 | (28-15+1)/28 = 14/28 | $1,000 × 14/28 = $500 |
| 3月 | - | 100% | $1,000 |
| **OTC** | 2月15日在Q1 | 全额 | $5,000 |
| **Q1 总计** | | | **$6,500** |

---

## 3. 周汇总计算

### 3.1 Weekly Metrics 数据结构

```python
class WeeklyMetrics(db.Model):
    owner_id = db.Column(db.Integer, nullable=False)  # 用户ID
    week_start = db.Column(db.Date, nullable=False)      # 周一日期
    
    # 五大指标
    leads_count = db.Column(db.Integer, default=0)           # Leads 数量（不含 Unqualified）
    pipeline_count = db.Column(db.Integer, default=0)        # Pipeline 数量（不含 Deal Lost）
    tcv = db.Column(db.Integer, default=0)                # TCV 总和（不含 Deal Lost）
    current_qtr_revenue = db.Column(db.Integer, default=0)  # 本季度收入
    next_qtr_revenue = db.Column(db.Integer, default=0)     # 下季度收入
```

---

### 3.2 汇总计算逻辑

```python
def recalculate_weekly_metrics(owner_id, ref_date=None):
    """
    重新计算并覆盖写入 weekly_metrics
    """
    week_start = get_week_start(ref_date)
    
    # 查询该 owner 本周所有 Pipeline
    pipelines = Pipeline.query.filter(
        Pipeline.owner_id == owner_id,
        Pipeline.date_added >= week_start
    ).all()
    
    # 计算指标
    leads_count = SalesLead.query.filter(
        SalesLead.owner_id == owner_id,
        SalesLead.date_added >= week_start,
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    pipeline_count = len([p for p in pipelines if p.stage != '6b) Deal Lost'])
    tcv = sum(p.tcv_usd or 0 for p in pipelines if p.stage != '6b) Deal Lost'])
    
    # 计算季度收入
    quarter_start, quarter_end = get_current_quarter_dates(ref_date)
    next_qtr_start, next_qtr_end = get_next_quarter_dates(ref_date)
    
    active_pipelines = [p for p in pipelines if p.stage not in ['6b) Deal Lost']]
    current_qtr_rev = calculate_quarter_revenue(active_pipelines, quarter_start, quarter_end)
    next_qtr_rev = calculate_quarter_revenue(active_pipelines, next_qtr_start, next_qtr_end)
```

---

### 3.3 周环比计算

```python
def get_dashboard_metrics(owner_id=None):
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(weeks=1)
    
    # 本周数据
    this_week = WeeklyMetrics.query.filter_by(
        owner_id=owner_id,
        week_start=this_monday
    ).first()
    
    # 上周数据（本周之前最近一条）
    last_week = WeeklyMetrics.query.filter(
        WeeklyMetrics.owner_id == owner_id,
        WeeklyMetrics.updated_at < this_monday
    ).order_by(WeeklyMetrics.updated_at.desc()).first()
    
    # 周环比
    vs_leads = this_week.leads_count - (last_week.leads_count if last_week else 0)
    vs_tcv = this_week.tcv - (last_week.tcv if last_week else 0)
```

**公式**:
```
周环比 = 本周累计 - 上周累计
```

---

## 4. 格式化函数

### 4.1 货币格式化

```python
def format_currency(value):
    """Format number as USD currency."""
    return f"${value:,}" if value is not None else '$0'

def format_currency_thousands(value):
    """Format number as USD currency with thousands separator, no decimals."""
    return f"${int(value):,}" if value is not None else "$0"
```

**示例**:
- `format_currency(1234567)` → `$1,234,567`
- `format_currency_thousands(1234567)` → `$1,234,567`

---

### 4.2 环比指示器

```python
def format_vs_indicator(current, previous):
    """Format VS indicator with arrow and percentage."""
    if previous == 0:
        if current > 0:
            return "↑ New", "success"
        return "—", "secondary"
    
    diff = current - previous
    pct = (diff / previous) * 100
    
    if diff > 0:
        return f"↑ {int(pct)}%", "success"
    elif diff < 0:
        return f"↓ {int(abs(pct))}%", "danger"
    return "—", "secondary"
```

---

## 5. 日期计算

### 5.1 获取季度日期

```python
def get_current_quarter_dates(reference_date=None):
    """
    Q1: 1-3月, Q2: 4-6月, Q3: 7-9月, Q4: 10-12月
    """
    quarter = (reference_date.month - 1) // 3  # 0=Q1, 1=Q2, 2=Q3, 3=Q4
    quarter_start_month = quarter * 3 + 1
    
    quarter_start = date(reference_date.year, quarter_start_month, 1)
    quarter_end = date(reference_date.year, quarter_start_month + 2, 
                      calendar.monthrange(reference_date.year, quarter_start_month + 2)[1])
```

---

### 5.2 获取下季度日期

```python
def get_next_quarter_dates(reference_date=None):
    """
    获取下季度的起止日期
    """
    next_quarter_month = ((reference_date.month - 1) // 3 + 1) * 3 + 1
    next_quarter_year = reference_date.year
    
    if next_quarter_month > 12:
        next_quarter_month -= 12
        next_quarter_year += 1
    
    # ... 计算 quarter_start 和 quarter_end
```

---

### 5.3 获取周一日期

```python
def get_week_start(ref_date=None):
    """获取本周一日期"""
    return ref_date - timedelta(days=ref_date.weekday())
```

---

## 附录 A: Pipeline 阶段说明

| 阶段 | 说明 | 计入收入？ |
|------|------|------------|
| 1) Prospecting | 初步接触 | ✅ (不含 Deal Lost) |
| 2) Lead Qualified | 线索合格 | ✅ (不含 Deal Lost) |
| 3) Demo/Meeting | 演示/会议 | ✅ (不含 Deal Lost) |
| 4) Proposal Submitted | 提案已提交 | ✅ (不含 Deal Lost) |
| 5) Negotiation | 谈判中 | ✅ (不含 Deal Lost) |
| 6a) Deal Won | 赢单 | ✅ |
| 6b) Deal Lost | 输单 | ❌ |
| 7) Activated | 已激活 | ✅ |

**规则**: 只有 **Deal Lost** 不计入收入，其他所有阶段都计入。

---

## 附录 B: 收入计算流程图

```
┌─────────────────────────────────────────────────────────┐
│                  Pipeline 数据                          │
│  (mrc_usd, otc_usd, est_act_date, stage)          │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              判断 stage != '6b) Deal Lost'             │
└─────────────────────┬───────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    ❌ 不计入               ✅ 继续计算
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────┐
│              计算 OTC                                      │
│  activation_date 在季度内? → OTC 全额                     │
│  activation_date 在季度外? → OTC = 0                     │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              计算 MRC (按月分摊)                          │
│  - activation_date < 月初 → 100%                        │
│  - activation_date 在月内 → 按比例                       │
│  - activation_date > 月底 → 0                           │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              季度收入 = OTC + MRC                        │
└─────────────────────────────────────────────────────────┘
```

---

## 变更日志

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2026-02-09 | 初始文档 |

