"""测试 CRM 日期解析修复"""
import sys
sys.path.insert(0, r"C:\Users\zhang\clawd\BITCRM")

from utils import validate_date

# 测试各种日期格式
test_dates = [
    '2025-03-28',   # YYYY-MM-DD
    '2025-08-14',
    '2025-09-04',
    '2025-10-21',
    '2025-11-18',
    '2025-11-27',
    '2025/03/28',   # YYYY/MM/DD
    'Jan 1, 2024',  # English format
    'Mar 28, 2025',
]

print('日期格式验证测试:')
print('='*50)
for date_str in test_dates:
    result = validate_date(date_str)
    if result:
        print(f'OK: {date_str:20} -> {result}')
    else:
        print(f'FAIL: {date_str:20} -> 解析失败')
print('='*50)
print('测试完成!')
