"""
CRM 日期格式修复脚本
用于将 Excel 文件中的 YYYY-MM-DD 格式日期转换为 CRM 系统兼容的格式
"""
import pandas as pd
from datetime import datetime
import os


def convert_date_format(input_file, output_file, date_columns):
    """
    转换 Excel 文件中的日期格式
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        date_columns: 需要转换的日期列名列表
    """
    # 读取 Excel 文件
    df = pd.read_excel(input_file)
    
    print(f"已读取文件: {input_file}")
    print(f"列名: {list(df.columns)}")
    print(f"总行数: {len(df)}")
    
    # 转换日期格式
    for col in date_columns:
        if col in df.columns:
            print(f"\n处理列: {col}")
            
            # 先尝试将所有值转换为字符串
            df[col] = df[col].astype(str)
            
            # 查找并转换日期
            converted_count = 0
            error_rows = []
            
            for idx, val in enumerate(df[col], start=1):
                val_clean = str(val).strip()
                
                # 跳过空值和 NaN
                if val_clean.lower() in ['nan', 'none', '', 'nat']:
                    df.at[idx-1, col] = ''
                    continue
                
                # 尝试多种日期格式
                date_formats = [
                    '%Y-%m-%d',           # 2025-03-28
                    '%Y/%m/%d',           # 2025/03/28
                    '%Y.%m.%d',           # 2025.03.28
                    '%m/%d/%Y',           # 03/28/2025
                    '%m-%d-%Y',           # 03-28-2025
                    '%B %d, %Y',          # March 28, 2025
                    '%b %d, %Y',          # Mar 28, 2025
                ]
                
                converted = False
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(val_clean, fmt).date()
                        # 转换为 'Jan 1, 2024' 格式
                        df.at[idx-1, col] = parsed_date.strftime('%b %d, %Y')
                        converted = True
                        converted_count += 1
                        break
                    except ValueError:
                        continue
                
                if not converted:
                    error_rows.append(idx)
            
            print(f"  成功转换: {converted_count} 行")
            if error_rows:
                print(f"  转换失败: {error_rows}")
        else:
            print(f"  列 '{col}' 不存在于文件中")
    
    # 保存转换后的文件
    df.to_excel(output_file, index=False)
    print(f"\n已保存文件: {output_file}")


def main():
    # 配置参数
    input_file = r"C:\Users\zhang\clawd\BITCRM\待导入的Leads数据.xlsx"  # 请修改为你的输入文件路径
    output_file = r"C:\Users\zhang\clawd\BITCRM\Leads_导入_已修复.xlsx"  # 输出文件路径
    date_columns = ['Date Added', 'date_added', 'date']  # 日期列名
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 - {input_file}")
        print("\n请修改 input_file 变量为你的 Excel 文件路径")
        return
    
    # 执行转换
    convert_date_format(input_file, output_file, date_columns)
    
    print("\n完成！请使用转换后的文件重新导入。")
    print(f"输出文件: {output_file}")


if __name__ == "__main__":
    main()
