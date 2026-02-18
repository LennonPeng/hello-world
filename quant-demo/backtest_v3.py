#!/usr/bin/env python3
"""
回测系统 v3 - 带图表
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# ============== 策略 ==============
class MAStrategy:
    """均线策略"""
    def __init__(self, short_ma=20, long_ma=60):
        self.short_ma = short_ma
        self.long_ma = long_ma
    
    def calculate(self, df):
        df = df.copy()
        df['ma_short'] = df['close'].rolling(self.short_ma).mean()
        df['ma_long'] = df['close'].rolling(self.long_ma).mean()
        df['golden_cross'] = (df['ma_short'] > df['ma_long']).astype(int)
        df['cross_change'] = df['golden_cross'].diff()
        return df
    
    def get_signal(self, df, i):
        if i < self.long_ma + 10:
            return 0
        if df.iloc[i]['cross_change'] == 1:
            return 1  # 买入
        elif df.iloc[i]['cross_change'] == -1:
            return -1  # 卖出
        return 0


def get_data(symbol):
    """获取数据"""
    df = ak.fund_etf_hist_em(
        symbol=symbol, 
        period='daily', 
        start_date='20150101', 
        end_date='20260217', 
        adjust='qfq'
    )
    
    # 列名映射
    col_map = {
        '日期': 'date', '开盘': 'open', '收盘': 'close',
        '最高': 'high', '最低': 'low', '成交量': 'volume',
        '成交额': 'amount', '振幅': 'amplitude', 
        '涨跌幅': 'pct_change', '涨跌额': 'change', 
        '换手率': 'turnover'
    }
    df = df.rename(columns=col_map)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def backtest_with_chart(symbol, name):
    """回测并绘图"""
    print(f"\n{'='*60}")
    print(f"回测: {name} ({symbol})")
    
    df = get_data(symbol)
    print(f"数据: {len(df)} 条 ({df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')})")
    
    # 计算指标
    strategy = MAStrategy(short_ma=20, long_ma=60)
    df = strategy.calculate(df)
    
    # 回测
    capital = 100000
    position = 0
    shares = 0
    entry_price = 0
    trades = []
    equity_curve = []
    
    for i in range(70, len(df)):
        date = df.iloc[i]['date']
        price = df.iloc[i]['close']
        
        signal = strategy.get_signal(df, i)
        
        # 买入
        if signal == 1 and position == 0:
            shares = int(capital / price)
            cost = shares * price
            capital -= cost
            position = 1
            entry_price = price
            trades.append({'date': date, 'action': 'BUY', 'price': price})
        
        # 卖出
        elif signal == -1 and position == 1:
            revenue = shares * price
            profit_pct = (price - entry_price) / entry_price * 100
            capital += revenue
            trades.append({'date': date, 'action': 'SELL', 'price': price, 'profit': profit_pct})
            position = 0
        
        # 记录权益
        if position == 1:
            equity = capital + shares * price
        else:
            equity = capital
        equity_curve.append({'date': date, 'equity': equity})
    
    # 最终平仓
    if position == 1:
        final = shares * df.iloc[-1]['close']
        capital += final
    
    total_return = (capital - 100000) / 100000 * 100
    years = len(df) / 252
    annual_return = ((capital / 100000) ** (1/max(years,0.1)) - 1) * 100
    
    print(f"收益: 总收益 {total_return:+.1f}% | 年化 {annual_return:+.1f}%")
    print(f"交易: {len(trades)} 次")
    
    # 绘图
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [3, 1, 1]})
    
    # 1. 价格 + 均线 + 买卖点
    ax1 = axes[0]
    ax1.plot(df['date'], df['close'], 'b-', linewidth=1, label='Price')
    ax1.plot(df['date'], df['ma_short'], 'g--', linewidth=0.8, label='MA20')
    ax1.plot(df['date'], df['ma_long'], 'r--', linewidth=0.8, label='MA60')
    
    # 标记买卖点
    buy_dates = [t['date'] for t in trades if t['action'] == 'BUY']
    buy_prices = [t['price'] for t in trades if t['action'] == 'BUY']
    sell_dates = [t['date'] for t in trades if t['action'] == 'SELL']
    sell_prices = [t['price'] for t in trades if t['action'] == 'SELL']
    
    ax1.scatter(buy_dates, buy_prices, marker='^', color='green', s=100, label='Buy', zorder=5)
    ax1.scatter(sell_dates, sell_prices, marker='v', color='red', s=100, label='Sell', zorder=5)
    
    ax1.set_title(f'{name} ({symbol}) - MA Strategy | Return: {total_return:+.1f}%', fontsize=14)
    ax1.set_ylabel('Price')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # 2. 权益曲线
    ax2 = axes[1]
    equity_df = pd.DataFrame(equity_curve)
    ax2.plot(equity_df['date'], equity_df['equity'], 'b-', linewidth=1)
    ax2.axhline(y=100000, color='gray', linestyle='--', alpha=0.5)
    ax2.set_ylabel('Equity')
    ax2.set_title('Equity Curve')
    ax2.grid(True, alpha=0.3)
    
    # 3. 涨跌
    ax3 = axes[2]
    ax3.bar(df['date'], df['pct_change'], color=['green' if x > 0 else 'red' for x in df['pct_change']], alpha=0.5)
    ax3.axhline(y=0, color='black', linewidth=0.5)
    ax3.set_ylabel('Change %')
    ax3.set_xlabel('Date')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存
    filename = f'/mnt/e/workspace/quant-demo/chart_{symbol}.png'
    plt.savefig(filename, dpi=100, bbox_inches='tight')
    plt.close()
    print(f"图表已保存: {filename}")
    
    # 最近交易
    if trades:
        print("最近交易:")
        for t in trades[-6:]:
            if t['action'] == 'BUY':
                print(f"  {t['date'].strftime('%Y-%m-%d')} 买入 @ {t['price']:.2f}")
            else:
                print(f"  {t['date'].strftime('%Y-%m-%d')} 卖出 @ {t['price']:.2f} ({t.get('profit', 0):+.1f}%)")
    
    return {
        'symbol': symbol,
        'name': name,
        'total_return': round(total_return, 2),
        'annual_return': round(annual_return, 2),
        'trades': len(trades)
    }


# ============== 主程序 ==============
if __name__ == "__main__":
    symbols = [
        ('510050', '上证50ETF'),
        ('510300', '沪深300ETF'),
        ('159919', '券商ETF'),
        ('512880', '半导体ETF'),
        ('515790', '光伏ETF'),
        ('159792', '科技创新ETF'),
    ]
    
    results = []
    for code, name in symbols:
        try:
            result = backtest_with_chart(code, name)
            results.append(result)
        except Exception as e:
            print(f"{name} 失败: {e}")
    
    # 汇总
    print("\n" + "="*60)
    print("回测汇总")
    print("="*60)
    for r in results:
        print(f"{r['name']}: 总收益 {r['total_return']:+.1f}% | 年化 {r['annual_return']:+.1f}% | 交易{r['trades']}次")
