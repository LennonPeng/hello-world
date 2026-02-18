#!/usr/bin/env python3
"""
历史回测系统 - 10年数据验证
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
import os
from pathlib import Path

# 加载配置
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ.setdefault(key, val)

from strategy_ensemble import TrendStrategy, MeanReversionStrategy, MarketRegimeDetector, Signal
from position_manager import RiskManager, Portfolio


# ============== 回测配置 ==============
class BacktestConfig:
    """回测配置"""
    # 时间范围：过去10年
    START_DATE = "20150101"
    END_DATE = datetime.now().strftime("%Y%m%d")
    
    # 初始资金
    INITIAL_CAPITAL = 100000
    
    # 手续费 (千分之1.5)
    COMMISSION_RATE = 0.0015
    
    # 滑点 (千分之1)
    SLIPPAGE = 0.001
    
    # 止损止盈 (优化参数)
    STOP_LOSS = -0.10      # -10% 放宽止损
    TAKE_PROFIT = 0.20     # +20% 提高止盈
    TRAILING_STOP = 0.08   # -8% 放宽追踪


# ============== 回测引擎 ==============
class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, symbol: str, name: str, initial_capital: float = 100000):
        self.symbol = symbol
        self.name = name
        self.initial_capital = initial_capital
        
        # 策略
        self.trend = TrendStrategy()
        self.reversion = MeanReversionStrategy()
        self.detector = MarketRegimeDetector()
        
        # 仓位管理
        self.risk = RiskManager(
            max_position_pct=0.3,
            max_loss_pct=BacktestConfig.STOP_LOSS,
            take_profit_pct=BacktestConfig.TAKE_PROFIT,
            trailing_stop_pct=BacktestConfig.TRAILING_STOP
        )
        
        # 组合
        self.portfolio = Portfolio(initial_capital)
        
        # 结果记录
        self.trades = []
        self.equity_curve = []
        self.current_position = 0  # 0=空仓, 1=持仓
        self.entry_price = 0
        
        # 统计数据
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
    
    def fetch_data(self, years: int = 10) -> pd.DataFrame:
        """获取历史数据"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y%m%d")
        
        print(f"  正在获取 {self.name} ({self.symbol}) 数据...")
        print(f"  时间范围: {start_date} ~ {end_date}")
        
        try:
            # 尝试获取ETF数据
            df = ak.fund_etf_hist_em(
                symbol=self.symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            df.columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount',
                         'amplitude', 'pct_change', 'change', 'turnover']
        except:
            try:
                # 尝试获取股票数据
                df = ak.stock_zh_a_hist(
                    symbol=self.symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
                df.columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount',
                             'amplitude', 'pct_change', 'change', 'turnover']
            except:
                # 获取指数数据
                df = ak.stock_zh_index_daily(symbol=self.symbol)
        
        # 标准化
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        print(f"  获取到 {len(df)} 条数据")
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = self.trend.calculate(df)
        df = self.reversion.calculate(df)
        return df
    
    def get_signal(self, df: pd.DataFrame, i: int) -> Signal:
        """获取交易信号"""
        if i < 60:
            return Signal.HOLD
        
        subset = df.iloc[:i+1]
        
        # 获取各策略信号
        trend_signal = self.trend.get_signal(subset)
        reversion_signal = self.reversion.get_signal(subset)
        
        # 检测市场状态
        regime = self.detector.detect(subset)
        
        # 综合评分 (根据市场状态调整)
        if regime.value == "trend_up":
            score = trend_signal.value * 0.7 + reversion_signal.value * 0.3
        elif regime.value == "trend_down":
            score = trend_signal.value * 0.7 + reversion_signal.value * 0.3
        else:  # 震荡市
            score = reversion_signal.value * 0.8 + trend_signal.value * 0.2
        
        # 提高阈值减少假信号
        if score > 0.5:
            return Signal.BUY
        elif score < -0.5:
            return Signal.SELL
        else:
            return Signal.HOLD
    
    def execute_trade(self, signal: Signal, price: float, date: str):
        """执行交易"""
        commission = price * BacktestConfig.COMMISSION_RATE
        slippage = price * BacktestConfig.SLIPPAGE
        
        if signal == Signal.BUY and self.current_position == 0:
            # 买入
            buy_price = price + commission + slippage
            max_shares = int(self.initial_capital * 0.3 / buy_price)  # 最多30%仓位
            
            if max_shares > 0:
                self.current_position = 1
                self.entry_price = buy_price
                self.total_trades += 1
                
                self.trades.append({
                    "date": date,
                    "action": "BUY",
                    "price": round(buy_price, 2),
                    "shares": max_shares
                })
        
        elif signal == Signal.SELL and self.current_position == 1:
            # 卖出
            sell_price = price - commission - slippage
            profit_pct = (sell_price - self.entry_price) / self.entry_price
            
            if profit_pct > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            
            self.trades.append({
                "date": date,
                "action": "SELL",
                "price": round(sell_price, 2),
                "shares": 0,
                "profit_pct": round(profit_pct * 100, 2)
            })
            
            self.current_position = 0
            self.entry_price = 0
    
    def check_stop_loss_take_profit(self, price: float, date: str) -> bool:
        """检查止损止盈"""
        if self.current_position == 0:
            return False
        
        profit_pct = (price - self.entry_price) / self.entry_price
        
        # 止损
        if profit_pct <= BacktestConfig.STOP_LOSS:
            self.execute_trade(Signal.SELL, price, date)
            return True
        
        # 止盈 (达到15%后启用追踪止损)
        if profit_pct >= BacktestConfig.TAKE_PROFIT:
            trailing_stop_price = price * (1 - BacktestConfig.TRAILING_STOP)
            if self.entry_price < trailing_stop_price:
                self.execute_trade(Signal.SELL, price, date)
                return True
        
        return False
    
    def run(self, df: pd.DataFrame) -> Dict:
        """运行回测"""
        print(f"\n{'='*60}")
        print(f"开始回测: {self.name} ({self.symbol})")
        print(f"时间范围: {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
        print(f"初始资金: {self.initial_capital:,.0f} 元")
        print(f"{'='*60}")
        
        # 计算指标
        df = self.calculate_indicators(df)
        
        # 逐日回测
        for i in range(len(df)):
            date = df.iloc[i]['date'].strftime('%Y-%m-%d')
            close = df.iloc[i]['close']
            
            # 检查止损止盈
            self.check_stop_loss_take_profit(close, date)
            
            # 获取信号并交易
            if self.current_position == 0:
                signal = self.get_signal(df, i)
                self.execute_trade(signal, close, date)
            
            # 记录权益
            if self.current_position == 1:
                equity = self.initial_capital * 0.3 + (close - self.entry_price) * (self.initial_capital * 0.3 / self.entry_price)
            else:
                equity = self.initial_capital
            
            self.equity_curve.append({
                "date": date,
                "equity": equity
            })
        
        # 强制平仓
        if self.current_position == 1:
            last_close = df.iloc[-1]['close']
            self.execute_trade(Signal.SELL, last_close, df.iloc[-1]['date'].strftime('%Y-%m-%d'))
        
        return self.generate_report()
    
    def generate_report(self) -> Dict:
        """生成回测报告"""
        if not self.equity_curve:
            return {}
        
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        
        # 计算收益率
        equity_df['return'] = equity_df['equity'].pct_change()
        
        # 年化收益率
        total_return = (equity_df['equity'].iloc[-1] - self.initial_capital) / self.initial_capital
        years = len(equity_df) / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 夏普比率
        if equity_df['return'].std() > 0:
            sharpe_ratio = equity_df['return'].mean() / equity_df['return'].std() * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # 最大回撤
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min()
        
        # 胜率
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        report = {
            "symbol": self.symbol,
            "name": self.name,
            "period": {
                "start": equity_df['date'].iloc[0].strftime('%Y-%m-%d'),
                "end": equity_df['date'].iloc[-1].strftime('%Y-%m-%d'),
                "trading_days": len(equity_df)
            },
            "performance": {
                "initial_capital": self.initial_capital,
                "final_equity": round(equity_df['equity'].iloc[-1], 2),
                "total_return": round(total_return * 100, 2),
                "annual_return": round(annual_return * 100, 2),
                "sharpe_ratio": round(sharpe_ratio, 2),
                "max_drawdown": round(max_drawdown * 100, 2)
            },
            "trading": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(win_rate * 100, 2)
            },
            "trades": self.trades[-20:]  # 最近20笔交易
        }
        
        return report


def print_report(report: Dict):
    """打印回测报告"""
    if not report:
        print("无回测数据")
        return
    
    print(f"\n{'='*60}")
    print(f"回测报告: {report['name']} ({report['symbol']})")
    print(f"{'='*60}")
    
    print(f"\n📅 回测期间")
    print(f"   {report['period']['start']} ~ {report['period']['end']}")
    print(f"   共 {report['period']['trading_days']} 个交易日")
    
    print(f"\n💰 收益表现")
    print(f"   初始资金: {report['performance']['initial_capital']:,.0f} 元")
    print(f"   最终权益: {report['performance']['final_equity']:,.2f} 元")
    print(f"   总收益率: {report['performance']['total_return']:+.2f}%")
    print(f"   年化收益率: {report['performance']['annual_return']:+.2f}%")
    print(f"   夏普比率: {report['performance']['sharpe_ratio']:.2f}")
    print(f"   最大回撤: {report['performance']['max_drawdown']:.2f}%")
    
    print(f"\n📊 交易统计")
    print(f"   总交易次数: {report['trading']['total_trades']}")
    print(f"   盈利次数: {report['trading']['winning_trades']}")
    print(f"   亏损次数: {report['trading']['losing_trades']}")
    print(f"   胜率: {report['trading']['win_rate']:.2f}%")
    
    if report['trades']:
        print(f"\n📝 最近交易记录:")
        for t in report['trades']:
            if t['action'] == 'BUY':
                print(f"   {t['date']} 买入 @ {t['price']}")
            else:
                print(f"   {t['date']} 卖出 @ {t['price']} (盈利: {t.get('profit_pct', 0):+.2f}%)")


# ============== 多标的回测 ==============
def run_multi_backtest():
    """多标的回测"""
    symbols = [
        # ETF
        {"code": "510050", "name": "上证50ETF"},
        {"code": "510300", "name": "沪深300ETF"},
        {"code": "159919", "name": "券商ETF"},
        {"code": "512880", "name": "半导体ETF"},
        # 指数
        {"code": "sh000016", "name": "上证50指数"},
        {"code": "sh000300", "name": "沪深300指数"},
    ]
    
    results = []
    
    for sym in symbols:
        try:
            engine = BacktestEngine(sym["code"], sym["name"], initial_capital=100000)
            df = engine.fetch_data(years=10)
            
            if len(df) > 1000:  # 确保有足够数据
                report = engine.run(df)
                results.append(report)
                
                # 保存单个报告
                with open(f"/mnt/e/workspace/quant-demo/backtest_{sym['code']}.json", "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            else:
                print(f"  数据不足，跳过")
        except Exception as e:
            print(f"  回测失败: {e}")
    
    # 汇总报告
    print("\n" + "="*60)
    print("多标的回测汇总")
    print("="*60)
    
    for r in results:
        if r:
            print(f"\n{r['name']}: 总收益 {r['performance']['total_return']:+.2f}%, 年化 {r['performance']['annual_return']:+.2f}%, 胜率 {r['trading']['win_rate']:.1f}%")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--multi":
        run_multi_backtest()
    else:
        # 单标的回测
        engine = BacktestEngine("510050", "上证50ETF", initial_capital=100000)
        df = engine.fetch_data(years=10)
        report = engine.run(df)
        print_report(report)
