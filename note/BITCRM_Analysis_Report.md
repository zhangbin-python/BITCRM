# BITCRM 项目软件开发报告

> 生成日期: 2026-02-10  
> 项目路径: C:\Users\zhang\clawd\BITCRM

---

## 目录

1. [项目概述](#1-项目概述)
2. [环境配置](#2-环境配置)
3. [技术架构](#3-技术架构)
4. [功能模块详解](#4-功能模块详解)
5. [数据逻辑分析](#5-数据逻辑分析)
6. [数据库设计](#6-数据库设计)
7. [API接口设计](#7-api接口设计)
8. [前端页面交互](#8-前端页面交互)
9. [核心算法与计算逻辑](#9-核心算法与计算逻辑)
10. [安全与权限](#10-安全与权限)
11. [部署与运维](#11-部署与运维)
12. [代码规范与最佳实践](#12-代码规范与最佳实践)

---

## 1. 项目概述

### 1.1 项目定位

BITCRM 是一个企业级客户关系管理系统（CRM），采用 Flask 框架构建的 Web 应用系统。该系统旨在帮助企业管理销售线索、管道销售、任务跟踪以及团队协作，提供完整的销售周期管理功能。

**核心业务目标：**
- 集中管理销售线索（Leads）
- 跟踪销售管道（Pipeline）各阶段进展
- 自动化计算关键业务指标（TCV、MRC、GP等）
- 提供多维度数据分析和报表
- 支持团队协作和权限管理

### 1.2 技术栈简介

| 类别 | 技术选型 | 版本 |
|------|----------|------|
| 后端框架 | Flask | 3.0.0 |
| ORM框架 | SQLAlchemy | 2.0.23 |
| 数据库 | PostgreSQL / SQLite | - |
| 前端框架 | Bootstrap 5 | - |
| 国际化 | Flask-Babel | 4.0.0 |
| 认证授权 | Flask-Login | 0.6.3 |
| 缓存 | Flask-Caching | 2.3.0 |
| 数据处理 | pandas / openpyxl | 2.1.4 / 3.1.2 |
| 部署服务器 | Gunicorn | 21.2.0 |

### 1.3 项目结构

```
BITCRM/
├── app.py                    # Flask应用工厂函数
├── config.py                 # 配置文件（开发/生产环境）
├── models.py                 # 数据库模型定义
├── routes.py                 # 路由和业务逻辑
├── utils.py                  # 工具函数（Excel、计算）
├── activity_logger.py        # 活动日志记录
├── extensions.py            # Flask扩展初始化
├── requirements.txt         # Python依赖
├── migrations/              # 数据库迁移文件
├── instance/                # 实例文件夹
│   ├── bitcrm.db           # SQLite数据库
│   └── uploads/            # 上传文件目录
├── templates/               # Jinja2模板
│   ├── base.html           # 基础模板
│   ├── dashboard.html      # 仪表板
│   ├── leads/              # 销售线索模块
│   ├── pipeline/           # 销售管道模块
│   ├── admin/              # 管理模块
│   └── partials/           # 可重用组件
├── static/                 # 静态资源
│   ├── css/                # 样式文件
│   └── js/                 # JavaScript文件
└── translations/           # 国际化翻译文件
    ├── en/                 # 英文翻译
    └── zh/                 # 中文翻译
```

---

## 2. 环境配置

### 2.1 开发环境要求

**操作系统：** Windows 10/11 或 Linux/macOS  
**Python版本：** 3.9 或更高版本（推荐 3.12）  
**内存要求：** 最低 2GB，推荐 4GB 以上  
**磁盘空间：** 最低 500MB可用空间

### 2.2 依赖配置

**核心依赖 (requirements.txt)：**

```python
# Web框架
Flask==3.0.0
Werkzeug==3.0.1

# Flask扩展
Flask-SQLAlchemy==3.1.1      # ORM支持
Flask-Babel==4.0.0          # 国际化
Flask-Login==0.6.3          # 用户认证
Flask-Migrate==4.0.5        # 数据库迁移
Flask-Caching==2.3.0        # 缓存支持

# 数据库
SQLAlchemy==2.0.23
psycopg2-binary==2.9.9       # PostgreSQL驱动

# 数据处理
pandas==2.1.4
openpyxl==3.1.2              # Excel读写

# 安全与配置
PyJWT==2.8.0
python-dotenv==1.0.0

# 部署
gunicorn==21.2.0
```

### 2.3 运行环境配置

**环境变量配置：**

```bash
# 必填配置
SECRET_KEY=<your-secret-key>          # 密钥（生产环境必须设置）
FLASK_APP=app.py                      # Flask应用入口
FLASK_ENV=development                 # 开发/生产环境

# 数据库配置
DATABASE_URL=postgresql://user:pass@host:5432/bitcrm
# 或使用SQLite
DATABASE_URL=sqlite:///bitcrm.db

# 数据库连接池配置
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# 缓存配置
CACHE_TYPE=SimpleCache
CACHE_DEFAULT_TIMEOUT=300
```

### 2.4 配置文件结构

**config.py 主要配置类：**

```python
class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key'
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 数据库连接池优化
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20,
    }
    
    # 国际化配置
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    LANGUAGES = ['en', 'zh']
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
```

---

## 3. 技术架构

### 3.1 整体架构

BITCRM 采用经典的 **Flask MVC 架构**：

```
┌─────────────────────────────────────────────────────┐
│                   Client Layer                       │
│              (Browser / Mobile)                      │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP Requests
┌─────────────────────▼───────────────────────────────┐
│                  Flask Application                    │
│  ┌─────────────┬─────────────┬─────────────────────┐  │
│  │   Routes    │  Templates  │     Controllers      │  │
│  │  (routes.py)│ (Jinja2)    │   (Business Logic)  │  │
│  └─────────────┴─────────────┴─────────────────────┘  │
│                        │                               │
│  ┌─────────────────────▼─────────────────────────────┐│
│  │              SQLAlchemy ORM                       ││
│  │            (Database Models)                      ││
│  └─────────────────────┬─────────────────────────────┘│
└───────────────────────┼────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────┐
│                   Database                             │
│             (PostgreSQL / SQLite)                      │
└────────────────────────────────────────────────────────┘
```

### 3.2 核心设计模式

**1. 应用工厂模式 (Application Factory)**

```python
# app.py
def create_app(config_class=None):
    """Flask应用工厂函数"""
    app = Flask(__name__)
    
    # 加载配置
    app.config.from_object(config)
    
    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app)
    
    # 注册蓝图
    from routes import main_bp, leads_bp, pipeline_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(leads_bp, url_prefix='/leads')
    app.register_blueprint(pipeline_bp, url_prefix='/pipeline')
    
    return app
```

**2. 蓝图模式 (Blueprint)**

系统使用多个蓝图模块化组织路由：

| 蓝图 | 路径 | 功能 |
|------|------|------|
| main_bp | / | 仪表板、登录登出、活动日志 |
| leads_bp | /leads | 销售线索CRUD、导入导出 |
| pipeline_bp | /pipeline | 销售管道管理、跟进记录 |
| tasks_bp | /tasks | 任务管理 |
| admin_bp | /admin | 用户管理 |
| api_bp | /api | RESTful API接口 |

**3. 数据仓库模式 (Repository)**

通过 SQLAlchemy 实现数据访问层抽象。

### 3.3 第三方库应用

| 库名 | 用途 | 关键功能 |
|------|------|----------|
| Flask-Babel | 国际化 | 多语言支持、日期格式化 |
| Flask-Login | 用户认证 | 会话管理、登录状态 |
| Flask-Migrate | 数据库迁移 | 版本控制、迁移执行 |
| pandas | 数据处理 | DataFrame、Excel操作 |
| openpyxl | Excel读写 | .xlsx文件处理 |
| SQLAlchemy | ORM | 模型定义、查询构建 |

---

## 4. 功能模块详解

### 4.1 用户认证模块

**功能概述：** 提供用户登录、登出、密码管理功能。

**核心特性：**
- 基于会话的认证（Flask-Login）
- 密码加密存储（bcrypt）
- 角色权限控制
- 语言偏好持久化

**用户角色：**

| 角色 | 描述 | 权限 |
|------|------|------|
| admin | 管理员 | 完全访问所有功能 |
| sales | 销售人员 | 仅访问自己的数据 |
| marketing | 市场人员 | 访问Leads相关数据 |

### 4.2 销售线索管理模块 (Leads)

**功能概述：** 管理和跟踪潜在客户信息。

**核心功能：**
- 创建/编辑/删除销售线索
- 状态跟踪（Qualified/Waiting for Response/Unqualified）
- 来源追踪（Website/Referral/Event等）
- 负责人分配
- 批量导入/导出 Excel
- 快速编辑（inline editing）

**状态流转：**

```
Waiting to be Contacted → Waiting for Response → Qualified/Unqualified
                                              ↓
                                     转换为 Pipeline
```

### 4.3 销售管道模块 (Pipeline)

**功能概述：** 跟踪销售机会从初始接触到成交的全过程。

**阶段定义：**

| 阶段 | 描述 | Win Rate |
|------|------|----------|
| 1) Prospecting | 潜在客户 | 10% |
| 2) Lead Qualified | 线索合格 | 20% |
| 3) Demo/Meeting | 演示/会议 | 30% |
| 4) Proposal Submitted | 已提交提案 | 50% |
| 5) Negotiation | 谈判中 | 70% |
| 6a) Deal Won | 成交 | 100% |
| 6b) Deal Lost | 丢单 | 0% |
| 7) Activated | 已激活 | 100% |

**关键字段：**
- **TCV (Total Contract Value)**：合同总价值
- **MRC (Monthly Recurring Cost)**：月度经常性成本
- **OTC (One-Time Cost)**：一次性成本
- **GP Margin**：毛利率
- **Est. Act. Date**：预计激活日期

### 4.4 任务管理模块 (Tasks)

**功能概述：** 管理和跟踪待办事项。

**任务状态：**
- In Progress（进行中）
- Overdue（已过期）
- Completed（已完成）

### 4.5 仪表板模块 (Dashboard)

**功能概述：** 展示关键业务指标和业绩概览。

**核心指标：**

1. **Leads Count**：本周新增线索数
2. **Qualified Leads**：合格线索数
3. **Pipeline Count**：管道机会数
4. **TCV**：合同总价值
5. **Current Qtr Revenue**：本季度收入
6. **Next Qtr Revenue**：下季度收入

### 4.6 管理模块 (Admin)

**功能概述：** 系统管理功能。

**功能列表：**
- 用户列表查看
- 创建/编辑用户
- 启用/禁用用户
- 重置用户密码
- 角色分配

---

## 5. 数据逻辑分析

### 5.1 业务数据流

**线索到管道转化流程：**

```
┌──────────────┐    状态变为 Qualified     ┌──────────────┐
│  SalesLead   │ ───────────────────────→ │   Pipeline   │
│  (线索池)    │                          │  (销售管道)  │
└──────────────┘                          └──────────────┘
                                               │
                                               │ 添加跟进
                                               ▼
                                         ┌──────────────┐
                                         │    Task      │
                                         │   (任务)     │
                                         └──────────────┘
```

### 5.2 数据处理规则

**1. 周汇总数据 (WeeklyMetrics)**

周汇总表按 owner_id + week_start 唯一标识，自动汇总以下指标：

| 字段 | 描述 | 计算规则 |
|------|------|----------|
| leads_count | 线索数量 | 不含 Unqualified 状态 |
| qualified_leads_count | 合格线索数 | 状态 = Qualified |
| pipeline_count | 管道数量 | 不含 Deal Lost |
| tcv | TCV总和 | 不含 Deal Lost |
| current_qtr_revenue | 本季度收入 | 按激活日期计算 |
| next_qtr_revenue | 下季度收入 | 按激活日期计算 |

**2. Pipeline 数据更新规则**

```python
def calculate_pipeline_metrics(pipeline):
    """计算Pipeline指标"""
    
    # TCV = MRC × 12 × 合同年限 + OTC
    pipeline.tcv_usd = (pipeline.mrc_usd * 12 * 
                       pipeline.contract_term_yrs) + pipeline.otc_usd
    
    # GP = TCV × 毛利率
    pipeline.gp = pipeline.tcv_usd * pipeline.gp_margin
    
    # MG (Margin Grade)
    if pipeline.gp_margin >= 0.5:
        pipeline.mg = 'A'
    elif pipeline.gp_margin >= 0.35:
        pipeline.mg = 'B'
    elif pipeline.gp_margin >= 0.2:
        pipeline.mg = 'C'
    else:
        pipeline.mg = 'D'
```

### 5.3 数据一致性保障

**1. 事务管理**

所有数据库操作使用事务包装。

**2. 锁机制**

防止多进程初始化用户数据。

**3. 缓存策略**

- 静态资源：1年缓存
- API响应：5分钟缓存
- HTML页面：不缓存

---

## 6. 数据库设计

### 6.1 表结构

#### users 表

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| id | INTEGER | PK | 主键 |
| username | VARCHAR(80) | UNIQUE, NOT NULL | 用户名 |
| email | VARCHAR(120) | UNIQUE | 邮箱 |
| password_hash | VARCHAR(256) | NOT NULL | 密码哈希 |
| role | VARCHAR(20) | NOT NULL, DEFAULT='sales' | 角色 |
| is_active | BOOLEAN | DEFAULT=True | 是否激活 |
| created_at | DATETIME | DEFAULT=now() | 创建时间 |
| updated_at | DATETIME | DEFAULT=now(), onupdate | 更新时间 |

#### sales_leads 表

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| id | INTEGER | PK | 主键 |
| name | VARCHAR(120) | NOT NULL | 姓名 |
| company | VARCHAR(200) | | 公司 |
| leads_status | VARCHAR(50) | NOT NULL, INDEX | 状态 |
| source | VARCHAR(50) | | 来源 |
| date_added | DATE | INDEX | 添加日期 |
| owner_id | INTEGER | FK->users.id | 负责人 |

#### pipeline 表

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| id | INTEGER | PK | 主键 |
| name | VARCHAR(120) | NOT NULL | 姓名 |
| company | VARCHAR(200) | | 公司 |
| owner_id | INTEGER | FK->users.id, NOT NULL | 负责人 |
| tcv_usd | FLOAT | DEFAULT=0 | 合同总价值 |
| mrc_usd | FLOAT | DEFAULT=0 | 月度经常性成本 |
| otc_usd | FLOAT | DEFAULT=0 | 一次性成本 |
| gp_margin | FLOAT | DEFAULT=0.0 | 毛利率 |
| gp | FLOAT | DEFAULT=0 | 毛利 |
| stage | VARCHAR(50) | DEFAULT='Prospecting', INDEX | 阶段 |

#### tasks 表

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| id | INTEGER | PK | 主键 |
| content | TEXT | NOT NULL | 任务内容 |
| due_date | DATE | | 截止日期 |
| status | VARCHAR(20) | DEFAULT='In Progress' | 状态 |
| owner_id | INTEGER | FK->users.id, NOT NULL | 负责人 |

#### weekly_metrics 表

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| id | INTEGER | PK | 主键 |
| owner_id | INTEGER | NULL=全公司汇总 | 负责人ID |
| week_start | DATE | NOT NULL, PK | 周一日期 |
| leads_count | INTEGER | DEFAULT=0 | 线索数 |
| pipeline_count | INTEGER | DEFAULT=0 | 管道数 |
| tcv | INTEGER | DEFAULT=0 | TCV总和 |

### 6.2 表关系图

```
users ──────► sales_leads ──────► pipeline ──────► tasks
   │                                    │
   │                                    ▼
   │                              pipeline_support
   │                                    │
   └────────────────────────────────────┘
```

### 6.3 索引设计

| 表名 | 索引字段 | 类型 | 描述 |
|------|----------|------|------|
| users | username | UNIQUE | 登录查询 |
| sales_leads | leads_status | INDEX | 状态筛选 |
| pipeline | stage | INDEX | 阶段筛选 |
| weekly_metrics | owner_id + week_start | UNIQUE | 主键索引 |

---

## 7. API 接口设计

### 7.1 RESTful API

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/change-password | 修改密码 |
| GET | /api/column-preferences/<page> | 获取列偏好 |
| POST | /api/column-preferences/<page> | 保存列偏好 |
| POST | /api/leads/<id>/quick-update | 快速更新线索 |
| GET | /api/dashboard/pipeline-kanban | 获取Kanban数据 |
| POST | /api/tasks/<id>/toggle-status | 切换任务状态 |
| GET | /api/activities/ | 获取活动列表 |
| GET | /api/activities/stats | 获取统计 |

### 7.2 请求响应格式

**成功响应示例：**

```json
{
    "success": true,
    "message": "操作成功",
    "data": {
        "id": 123,
        "name": "Example Company"
    }
}
```

**错误响应示例：**

```json
{
    "success": false,
    "error": "无权访问销售线索"
}
```

---

## 8. 前端页面交互

### 8.1 页面结构

**基础模板 (base.html)**

```
┌─────────────────────────────────────────────────────┐
│ Header (导航栏)                                     │
│  - Logo                                            │
│  - 导航菜单 (Dashboard, Leads, Pipeline, Tasks)    │
│  - 语言切换                                        │
│  - 用户菜单                                        │
├─────────────────────────────────────────────────────┤
│ Content Block                                      │
│  - Page Title                                      │
│  - 页面内容                                        │
├─────────────────────────────────────────────────────┤
│ Footer                                             │
└─────────────────────────────────────────────────────┘
```

### 8.2 核心组件

**1. 数据表格组件 (Leads/Pipeline)**

功能特性：
- 可配置的列显示/隐藏
- 排序功能
- 分页浏览
- 快速筛选
- 自定义列偏好持久化

**2. Kanban看板组件 (Pipeline)**

功能特性：
- 拖拽式阶段变更
- 卡片式展示
- 实时数据更新
- 筛选和搜索

**3. 模态框组件**

- 跟进记录模态框
- 列设置模态框
- 确认删除模态框
- 用户编辑模态框

---

## 9. 核心算法与计算逻辑

### 9.1 TCV 计算算法

**公式：**

```
TCV = MRC × 12 × ContractTerm + OTC
```

**示例：**
- MRC = $1,000/月
- OTC = $5,000
- ContractTerm = 3年

```
TCV = 1,000 × 12 × 3 + 5,000 = $41,000
```

### 9.2 季度收入计算算法

**本季度收入计算规则：**
- OTC：激活日期在季度内才累加
- MRC：按激活日期分月计算

**毛利等级划分：**

| 毛利率 | 等级 | 说明 |
|--------|------|------|
| ≥ 50% | A | 高利润 |
| 35% - 49% | B | 中高利润 |
| 20% - 34% | C | 中等利润 |
| < 20% | D | 低利润 |

---

## 10. 安全与权限

### 10.1 认证授权

**1. 用户认证**

- 密码使用 Werkzeug security 生成哈希
- 会话管理使用 Flask-Login
- 支持角色权限检查

**2. 权限控制**

```python
def can_access_leads(self):
    """检查是否可以访问销售线索"""
    return self.is_admin() or self.is_marketing()

def can_access_pipeline(self, pipeline):
    """检查是否可以访问特定管道"""
    if self.is_admin():
        return True
    if pipeline.owner_id == self.id:
        return True
    if self in pipeline.support_team:
        return True
    return False
```

### 10.2 数据安全

**1. SQL注入防护**

- 使用 SQLAlchemy 参数化查询
- ORM 自动处理转义

**2. XSS防护**

- Jinja2 模板自动转义
- 手动标记安全内容

**3. CSRF防护**

- Flask-WTF 表单令牌

### 10.3 HTTP安全头

```python
response.headers['X-Frame-Options'] = 'SAMEORIGIN'
response.headers['X-XSS-Protection'] = '1; mode=block'
response.headers['X-Content-Type-Options'] = 'nosniff'
```

---

## 11. 部署与运维

### 11.1 部署方式

**1. 开发环境**

```bash
cd C:\Users\zhang\clawd\BITCRM
venv\Scripts\activate
pip install -r requirements.txt
flask run
```

**2. 生产环境 (Gunicorn)**

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**3. Docker 部署**

提供 Dockerfile 和 docker-compose.yml。

### 11.2 数据库迁移

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 11.3 日志配置

系统通过 activity_logger.py 记录所有用户操作。

---

## 12. 代码规范与最佳实践

### 12.1 代码风格

**1. 命名规范**

- 类名：PascalCase（User, SalesLead）
- 函数/变量：snake_case（get_locale, calculate_tcv）
- 常量：UPPER_SNAKE_CASE（DATABASE_URL）

**2. 注释规范**

```python
def calculate_pipeline_metrics(pipeline):
    """
    Calculate and update pipeline metrics.
    
    Args:
        pipeline: Pipeline model instance
    """
```

### 12.2 最佳实践

**1. 错误处理**

```python
try:
    db.session.commit()
except Exception as e:
    db.session.rollback()
    flash(f'Error: {str(e)}', 'danger')
```

**2. 数据库优化**

- 使用连接池
- 添加必要索引
- 避免 N+1 查询

**3. 缓存策略**

- 合理设置缓存时间
- 分离静态资源和动态内容

---

## 附录

### A. 默认用户

| 角色 | 用户名 | 密码 |
|------|--------|------|
| Admin | Bruce | bitcrm |
| Admin | Admin | bitcrm |
| Sales | Eric | bitcrm |
| Sales | Anthony | bitcrm |
| Sales | Joseph | bitcrm |
| Sales | Romeo | bitcrm |

### B. 状态选项

**Leads Status:**
- Qualified
- Waiting for Response
- Unqualified
- Waiting to be Contacted

**Pipeline Stage:**
- 1) Prospecting
- 2) Lead Qualified
- 3) Demo/Meeting
- 4) Proposal Submitted
- 5) Negotiation
- 6a) Deal Won
- 6b) Deal Lost
- 7) Activated

---

**文档结束**

> 本报告由 OpenClaw 自动生成
> 如有问题请联系系统管理员
