@echo off
cd /d C:\Users\zhang\clawd\BITCRM
del .git\index.lock 2>nul
git add -A
git commit -m "optimize dashboard performance"
git push
pause
