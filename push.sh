#!/bin/bash

# macOS/Linux 一键更新脚本
# 用法: ./push.sh

echo "========================================"
echo "         🚀 BITCRM 一键更新并推送"
echo "========================================"
echo ""

echo "[1/4] 正在添加修改的文件..."
git add .

echo ""
echo "[2/4] 请输入提交说明（直接回车使用默认说明）:"
read -p "> " commit_msg
if [ -z "$commit_msg" ]; then
    commit_msg="更新 BITCRM $(date '+%Y-%m-%d %H:%M')"
fi

echo ""
echo "[3/4] 正在提交..."
git commit -m "$commit_msg"

echo ""
echo "[4/4] 正在推送到 GitHub..."
git push origin main

echo ""
echo "========================================"
echo "✅ 完成！代码已推送到 GitHub"
echo "========================================"
