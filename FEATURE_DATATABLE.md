# CRM 多维表格改造计划

## 目标
把 Sales Leads、Pipelines、Tasks、Users 列表页面改造成类似飞书多维表格体验

## 功能清单
1. ✅ 用户可以自定义显示哪些字段
2. ✅ 用户可以拖拽调整字段顺序
3. ✅ 记住用户选择（存到数据库）
4. ✅ 表格保持服务端渲染

## 技术方案

### 后端改动
1. User 模型添加 `column_preferences` JSON 字段
2. 创建 API 路由：
   - `GET /api/column-preferences/<page>` - 获取用户配置
   - `POST /api/column-preferences/<page>` - 保存用户配置
3. 修改列表视图，传递可用字段列表

### 前端改动
1. base.html 引入 SortableJS
2. 创建字段设置组件（Offcanvas）
3. 修改列表模板，支持动态列渲染
4. 拖拽后自动保存配置

## 字段定义

### Sales Leads 可用字段
- name, company, industry, position, email, mobile_number
- leads_status, source, event, date_added
- owner_id (显示 owner.username)
- requirements, note
- created_at, updated_at

### Pipeline 可用字段
- name, company, industry, position, email, mobile_number
- owner_id (显示 owner.username)
- product, tcv_usd, mrc_usd, otc_usd
- stage, level, win_rate
- est_sign_date, est_act_date
- stuckpoint, comments
- created_at, updated_at

### Tasks 可用字段
- content, due_date, status
- owner_id (显示 owner.username)
- pipeline_id (显示关联公司)
- company, created_at, updated_at

### Users 可用字段
- username, email, role, is_active, created_at

## 开发顺序
1. 修改 User 模型，添加 column_preferences 字段
2. 创建列配置 API 路由
3. base.html 引入 SortableJS
4. 创建字段设置 Offcanvas 组件
5. 修改 Sales Leads 列表（第一个试点）
6. 复制到 Pipeline、Tasks、Users 页面
