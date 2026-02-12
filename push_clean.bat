@echo off
cd /d C:\Users\zhang\clawd\BITCRM
git add .
git commit -m "Initial commit - BITCRM only"
git remote remove origin 2>nul
git remote add origin https://github.com/zhangbin-python/BITCRM.git
git push -u origin master
pause
