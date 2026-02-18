#!/usr/bin/env python3
"""
改进版回测系统 - 优化策略
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import json
import traceback

# ============== 简单但有效的策略 ==============
class ImprovedStrategy:
    """改进版策略"""
    
    def __init__(self, short_ma=20, long_ma=60):
        self.short_ma = short_ma
        self.long_ma = long_ma
    
    def calculate(self, df):
        """计算指标"""
        df = df.copy()
        df['ma_short'] = df['close'].rolling(self.short_ma).mean()
        df['ma_long'] = df['close'].rolling(self.long_ma).mean()
        
        # 突破20日高低点
        df['high20'] = df['high'].rolling(20).max()
        df['low20'] = df['low'].rolling(20).min()
        
        # 均线多头排列
        df['golden_cross'] = (df['ma_short'] > df['ma_long']).astype(int)
        df['cross_change'] = df['golden_cross'].diff()
        
        return df
    
    def get_signal(self, df, i):
        """获取信号"""
        if i < self.long_ma + 10:
            return 0  # HOLD
        
        # 金叉买入
        if df.iloc[i]['cross_change'] == 1:
            return 1  # BUY
        # 死叉卖出
        elif df.iloc[i]['cross_change'] == -1:
            return -1  # SELL
        else:
            return 0  # HOLD


def simple_backtest(symbol, name, years=10):
    """简化版回测"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y%m%d")
    
    print(f"\n{'='*60}")
    print(f"回测: {name} ({symbol})")
    
    try:
        # 获取数据
        if len(symbol) == 6 and symbol.isdigit():
            df = ak.stock_zh_a_hist(symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        else:
            df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        
        # 处理列名 - 根据实际列数
        col_count = len(df.columns)
        col_map = {
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', 
            '涨跌幅': 'pct_change', '涨跌额': 'change', 
            '换手率': 'turnover'
        }
        new_cols = [col_map.get(c, c) for c in df.columns]
        df.columns = new_cols
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        print(f"数据: {len(df)} 条 ({df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')})")
        
        # 计算指标
        strategy = ImprovedStrategy(short_ma=20, long_ma=60)
        df = strategy.calculate(df)
        
        # 回测
        capital = 100000
        position = 0
        shares = 0
        entry_price = 0
        trades = []
        
        for i in range(70, len(df)):
            date = df.iloc[i]['date'].strftime('%Y-%m-%d')
            price = df.iloc[i]['close']
            
            signal = strategy.get_signal(df, i)
            
            # 买入
            if signal == 1 and position == 0:
                shares = int(capital / price)
                cost = shares * price
                capital -= cost
                position = 1
                entry_price = price
                trades.append(f"{date} 买入 {shares}股 @ {price:.2f}")
            
            # 卖出
            elif signal == -1 and position == 1:
                revenue = shares * price
                profit_pct = (price - entry_price) / entry_price * 100
                capital += revenue
                trades.append(f"{date} 卖出 @ {price:.2f} ({(profit_pct):+.1f}%)")
                position = 0
                shares = 0
        
        # 最终持仓
        if position == 1:
            final_value = shares * df.iloc[-1]['close']
            capital += final_value
        
        total_return = (capital - 100000) / 100000 * 100
        years = len(df) / 252
        annual_return = ((capital / 100000) ** (1/years) - 1) * 100 if years > 0 else 0
        
        print(f"\n💰 收益:")
        print(f"   初始: 100,000")
        print(f"   最终: {capital:,.0f}")
        print(f"   总收益: {total_return:+.1f}%")
        print(f"   年化: {annual_return:+.1f}%")
        
        # 统计交易
        buy_count = sum(1 for t in trades if '买入' in t)
        sell_count = sum(1 for t in trades if '卖出' in t)
        print(f"   交易次数: 买入{buy_count}次, 卖出{sell_count}次")
        
        if trades:
            print(f"\n📝 最近10笔交易:")
            for t in trades[-10:]:
                print(f"   {t}")
        
        return {
            "symbol": symbol,
            "name": name,
            "data_days": len(df),
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "trades": len(trades),
            "trades_detail": trades[-20:]
        }
        
    except Exception as e:
        print(f"错误: {e}")
        traceback.print_exc()
        return None


# ============== 主程序 ==============
if __name__ == "__main__":
    # 测试多个标的
    symbols = [
        ("510050", "上证50ETF"),
        ("510300", "沪深300ETF"),
        ("159919", "券商ETF"),
        ("512880", "半导体ETF"),
        ("515790", "光伏ETF"),
        ("159792", "科技创新ETF"),
    ]
    
    results = []
    for code, name in symbols:
        try:
            result = simple_backtest(code, name, years=10)
            if result:
                results.append(result)
        except Exception as e:
            print(f"{name} 回测失败: {e}")
    
    # 汇总
    print("\n" + "="*60)
    print("回测汇总")
    print("="*60)
    for r in results:
        if r:
            print(f"{r['name']}: 总收益 {r['total_return']:+.1f}% | 年化 {r['annual_return']:+.1f}%")
