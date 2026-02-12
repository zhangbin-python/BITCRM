#!/bin/bash

# BITCRM 一键部署脚本
# 用法: curl -sL https://raw.githubusercontent.com/zhangbin-python/BITCRM/main/deploy.sh | bash

set -e

echo "🚀 开始部署 BITCRM..."

# 检查系统
if [ ! -f /etc/debian_version ]; then
    echo "❌ 当前脚本仅支持 Debian/Ubuntu 系统"
    exit 1
fi

# 1. 安装 Python 和依赖
echo "📦 安装系统依赖..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git

# 2. 创建目录
echo "📁 创建应用目录..."
mkdir -p /var/www/bitcrm
cd /var/www/bitcrm

# 3. 拉取代码
echo "📥 下载代码..."
if [ -d ".git" ]; then
    git pull
else
    git clone https://github.com/zhangbin-python/BITCRM.git .
fi

# 4. 创建虚拟环境
echo "🐍 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 5. 安装 Python 依赖
echo "📦 安装 Python 依赖..."
pip install -r requirements.txt

# 6. 配置环境变量
echo "⚙️ 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  请编辑 /var/www/bitcrm/.env 配置密钥和数据库"
fi

# 7. 初始化数据库
echo "🗄️ 初始化数据库..."
export FLASK_APP=app.py
flask db upgrade 2>/dev/null || true

# 8. 创建日志目录
mkdir -p logs

# 9. 设置权限
chown -R www-data:www-data /var/www/bitcrm
chmod -R 755 /var/www/bitcrm

echo ""
echo "✅ 部署完成！"
echo ""
echo "📝 下一步操作："
echo "   1. 编辑配置: nano /var/www/bitcrm/.env"
echo "   2. 启动服务: systemctl daemon-reload && systemctl start bitcrm"
echo "   3. 查看状态: systemctl status bitcrm"
echo ""
