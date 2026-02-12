import psycopg2  
import pandas as pd  
from datetime import datetime  
import os  
# 数据库连接信息  
DB_HOST = 'postgresql.zeabur.app'  
DB_PORT = 5432  
DB_USER = 'root'  
DB_PASSWORD = '61MHo39r4alPg5Kf78bwyTF0zxcN2qhp'  
DB_NAME = 'zeabur'  
# 创建导出文件名  
export_file = f'database_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'  
print(f"✓ 导出文件: {export_file}")  
print()  
try:  
    # 连接到数据库  
    print("正在连接到 PostgreSQL 数据库...")  
    conn = psycopg2.connect(  
        host=DB_HOST,  
        port=DB_PORT,  
        user=DB_USER,  
        password=DB_PASSWORD,  
        database=DB_NAME  
    )  
    print("✓ 连接成功\n")  
      
    cursor = conn.cursor()  
      
    # 获取所有表  
    cursor.execute("""  
        SELECT table_name   
        FROM information_schema.tables   
        WHERE table_schema = 'public'  
        ORDER BY table_name  
    """)  
      
    tables = [row[0] for row in cursor.fetchall()]  
    print(f"找到 {len(tables)} 个表:\n")  
      
    # 创建 Excel 写入器  
    with pd.ExcelWriter(export_file, engine='openpyxl') as writer:  
        for table_name in tables:  
            print(f"正在导出表: {table_name}...", end=" ")  
              
            try:  
                # 使用 pandas 读取表数据  
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)  
                  
                # 写入 Excel  
                df.to_excel(writer, sheet_name=table_name, index=False)  
                  
                print(f"✓ ({len(df)} 行)")  
                  
            except Exception as e:  
                print(f"✗ 错误: {e}")  
      
    cursor.close()  
    conn.close()  
      
    file_size = os.path.getsize(export_file)  
    print(f"\n✓ 导出完成！")  
    print(f"✓ 文件: {export_file}")  
    print(f"✓ 大小: {file_size / 1024:.2f} KB")  
except psycopg2.Error as e:  
    print(f"✗ 数据库错误: {e}")  
except Exception as e:  
    print(f"✗ 错误: {e}")  
