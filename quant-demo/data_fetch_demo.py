#!/usr/bin/env python3
"""
数据采集 Demo - 验证 A股/ETF 数据获取可行性
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("数据采集可行性验证 Demo")
print("=" * 60)

# ============ 1. A股股票数据测试 ============
print("\n[1] 测试 A股 股票数据获取...")
try:
    # 获取茅台日线数据
    df_stock = ak.stock_zh_a_hist(symbol="600519", period="daily", 
                                    start_date="20250101", end_date="20250216",
                                    adjust="qfq")
    print(f"✅ A股数据获取成功!")
    print(f"   股票: 贵州茅台(600519)")
    print(f"   数据条数: {len(df_stock)}")
    print(f"   列名: {list(df_stock.columns)}")
    print(f"   最新数据:\n{df_stock.tail(3)}")
except Exception as e:
    print(f"❌ A股数据获取失败: {e}")

# ============ 2. ETF 数据测试 ============
print("\n[2] 测试 ETF 数据获取...")
try:
    # 获取ETF列表
    df_etf = ak.fund_etf_spot_em()
    print(f"✅ ETF数据获取成功!")
    print(f"   ETF数量: {len(df_etf)}")
    print(f"   列名: {list(df_etf.columns)[:10]}...")
    print(f"   示例ETF:\n{df_etf.head(3)}")
except Exception as e:
    print(f"❌ ETF列表获取失败: {e}")

# ============ 3. ETF 日线数据测试 ============
print("\n[3] 测试 ETF 日线数据获取...")
try:
    # 获取上证50ETF (510050)
    df_etf_daily = ak.fund_etf_hist_em(symbol="510050", 
                                         period="daily",
                                         start_date="20250101",
                                         end_date="20250216",
                                         adjust="qfq")
    print(f"✅ ETF日线数据获取成功!")
    print(f"   ETF: 510050 上证50ETF")
    print(f"   数据条数: {len(df_etf_daily)}")
    print(f"   最新数据:\n{df_etf_daily.tail(3)}")
except Exception as e:
    print(f"❌ ETF日线获取失败: {e}")

# ============ 4. 实时行情测试 ============
print("\n[4] 测试 实时行情获取...")
try:
    # 获取实时行情
    df_realtime = ak.stock_zh_a_spot_em()
    print(f"✅ 实时行情获取成功!")
    print(f"   股票数量: {len(df_realtime)}")
    print(f"   列名: {list(df_realtime.columns)[:8]}...")
except Exception as e:
    print(f"❌ 实时行情获取失败: {e}")

# ============ 5. 指数数据测试 ============
print("\n[5] 测试 指数数据获取...")
try:
    # 获取上证指数
    df_index = ak.stock_zh_index_daily(symbol="sh000001")
    print(f"✅ 指数数据获取成功!")
    print(f"   指数: 上证指数(sh000001)")
    print(f"   数据条数: {len(df_index)}")
    print(f"   最新数据:\n{df_index.tail(3)}")
except Exception as e:
    print(f"❌ 指数数据获取失败: {e}")

print("\n" + "=" * 60)
print("数据采集可行性验证完成")
print("=" * 60)
