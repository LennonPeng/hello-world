#!/usr/bin/env python3
"""
Phase 2: 多标的监控系统
- 监控 ETF、指数、个股
- 每半小时分析一次
- 交易日自动运行
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
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

from strategy_ensemble import *

# 辅助函数
def llm_signal_value(signal: str) -> float:
    """将 LLM 信号转换为数值"""
    if signal == "BUY":
        return 1.0
    elif signal == "SELL":
        return -1.0
    else:
        return 0.0

# ============== 监控标的配置 ==============
class MonitorConfig:
    """监控标的列表"""
    
    # 指数
    INDEXES = [
        {"code": "sh000001", "name": "上证指数"},
        {"code": "sh000016", "name": "上证50"},
        {"code": "sh000300", "name": "沪深300"},
        {"code": "sz399001", "name": "深证成指"},
        {"code": "sz399006", "name": "创业板指"},
    ]
    
    # ETF (热门)
    ETFS = [
        {"code": "510050", "name": "上证50ETF"},
        {"code": "510300", "name": "沪深300ETF"},
        {"code": "159919", "name": "券商ETF"},
        {"code": "512880", "name": "半导体ETF"},
        {"code": "159995", "name": "券商ETF"},
        {"code": "159792", "name": "科技创新ETF"},
        {"code": "515790", "name": "光伏ETF"},
    ]
    
    # 个股 (热门)
    STOCKS = [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000858", "name": "五粮液"},
        {"code": "601318", "name": "中国平安"},
        {"code": "600036", "name": "招商银行"},
        {"code": "000333", "name": "美的集团"},
        {"code": "002594", "name": "比亚迪"},
        {"code": "300750", "name": "宁德时代"},
    ]
    
    @classmethod
    def get_all(cls) -> List[Dict]:
        return cls.INDEXES + cls.ETFS + cls.STOCKS


# ============== 数据获取 ==============
class MarketDataFetcher:
    """市场数据获取"""
    
    # 列名映射
    COLUMN_MAP = {
        '日期': 'date', '开盘': 'open', '收盘': 'close',
        '最高': 'high', '最低': 'low', '成交量': 'volume',
        '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_change',
        '涨跌额': 'change', '换手率': 'turnover'
    }
    
    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名"""
        # 尝试映射中文列名
        cols = df.columns.tolist()
        new_cols = []
        for c in cols:
            if c in MarketDataFetcher.COLUMN_MAP:
                new_cols.append(MarketDataFetcher.COLUMN_MAP[c])
            else:
                new_cols.append(c)
        df.columns = new_cols
        
        # 确保有 date 和 close 列
        if 'date' in df.columns and 'close' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
        
        return df
    
    @staticmethod
    def get_index_daily(code: str, days: int = 60) -> pd.DataFrame:
        """获取指数日线"""
        df = ak.stock_zh_index_daily(symbol=code)
        df = MarketDataFetcher.normalize_columns(df)
        df = df.tail(days)
        return df
    
    @staticmethod
    def get_etf_daily(code: str, days: int = 60) -> pd.DataFrame:
        """获取ETF日线"""
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=(datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq"
            )
            df = MarketDataFetcher.normalize_columns(df)
            df = df.tail(days)
            return df
        except Exception as e:
            print(f"Error getting ETF {code}: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def get_stock_daily(code: str, days: int = 60) -> pd.DataFrame:
        """获取股票日线"""
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=(datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq"
            )
            df = MarketDataFetcher.normalize_columns(df)
            df = df.tail(days)
            return df
        except Exception as e:
            print(f"Error getting stock {code}: {e}")
            return pd.DataFrame()
    
    @classmethod
    def fetch(cls, item: Dict, days: int = 60) -> pd.DataFrame:
        """根据类型获取数据"""
        code = item["code"]
        
        # 判断类型：指数以 sh/sz 开头且后面是数字
        if code.startswith(("sh", "sz")) and code[2:].isdigit():
            # 指数 (如 sh000001, sh000016, sz399001)
            return cls.get_index_daily(code, days)
        elif code.startswith(("5", "1", "15", "16", "51", "52")) and len(code) == 6:
            # ETF (如 510050, 159919, 512880)
            return cls.get_etf_daily(code, days)
        elif code.isdigit() and len(code) == 6:
            # 股票
            return cls.get_stock_daily(code, days)
        else:
            # 默认当作 ETF
            return cls.get_etf_daily(code, days)


# ============== 扫描引擎 ==============
class ScannerEngine:
    """扫描引擎"""
    
    def __init__(self):
        self.trend = TrendStrategy()
        self.reversion = MeanReversionStrategy()
        self.llm = LLMStrategy()
        self.detector = MarketRegimeDetector()
    
    def analyze(self, item: Dict) -> Dict:
        """分析单个标的"""
        code = item["code"]
        name = item["name"]
        
        try:
            # 获取数据
            df = MarketDataFetcher.fetch(item, days=60)
            
            # 调试：打印获取的数据
            if len(df) < 5:
                return {"code": code, "name": name, "error": f"数据不足: {len(df)}条"}
            
            # 重置索引
            df = df.reset_index(drop=True)
            
            # 计算指标
            df = self.trend.calculate(df)
            df = self.reversion.calculate(df)
            
            # 获取信号
            regime = self.detector.detect(df)
            
            # 趋势信号
            trend_signal = self.trend.get_signal(df)
            
            # 均值回归信号
            reversion_signal = self.reversion.get_signal(df)
            
            # 综合评分
            score = trend_signal.value * 0.5 + reversion_signal.value * 0.5
            
            # LLM 信号：只在有信号时调用 (仅记录，不影响评分)
            llm_signal = "SKIP"
            llm_reason = ""
            # if self.llm.api_key and (score > 0.3 or score < -0.3):
            #     try:
            #         llm_result = self.llm.analyze_technical(df, code)
            #         llm_signal = llm_result.get("signal", Signal.HOLD).name
            #         llm_reason = llm_result.get("reason", "")[:150]
            #     except Exception as e:
            #         llm_signal = f"ERROR"
            
            if score > 0.3:
                signal = "BUY"
            elif score < -0.3:
                signal = "SELL"
            else:
                signal = "HOLD"
            
            latest = df.iloc[-1]
            
            return {
                "code": code,
                "name": name,
                "close": round(latest['close'], 2),
                "pct_change": round(latest.get('pct_change', 0), 2),
                "regime": regime.value,
                "trend": trend_signal.name,
                "reversion": reversion_signal.name,
                "llm": llm_signal,
                "llm_reason": llm_reason,
                "signal": signal,
                "score": round(score, 2),
                "ma_cross": "金叉" if latest.get('ma_short', 0) > latest.get('ma_long', 0) else "死叉",
            }
            
        except Exception as e:
            return {"code": code, "name": name, "error": str(e)}


# ============== 机会筛选 ==============
class OpportunityFinder:
    """机会发现器"""
    
    @staticmethod
    def find_opportunities(results: List[Dict]) -> Dict:
        """从结果中筛选机会"""
        opportunities = {
            "buy_signals": [],
            "sell_signals": [],
            "watch_list": []
        }
        
        for r in results:
            if "error" in r:
                continue
            
            if r["signal"] == "BUY":
                opportunities["buy_signals"].append(r)
            elif r["signal"] == "SELL":
                opportunities["sell_signals"].append(r)
            
            # 添加到观察列表
            opportunities["watch_list"].append({
                "code": r["code"],
                "name": r["name"],
                "signal": r["signal"],
                "score": r["score"]
            })
        
        return opportunities


# ============== 主扫描 ==============
def run_scan():
    """运行扫描"""
    print("=" * 70)
    print(f"多标的监控系统 - 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 获取所有监控标的
    items = MonitorConfig.get_all()
    print(f"\n监控标的数量: {len(items)}")
    print(f"  - 指数: {len(MonitorConfig.INDEXES)}")
    print(f"  - ETF: {len(MonitorConfig.ETFS)}")
    print(f"  - 个股: {len(MonitorConfig.STOCKS)}")
    
    # 扫描
    engine = ScannerEngine()
    results = []
    
    print("\n[1] 正在分析各标的...")
    for i, item in enumerate(items):
        result = engine.analyze(item)
        results.append(result)
        
        signal = result.get("signal", "ERROR")
        signal_emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"
        print(f"  {i+1}. {result.get('name', 'N/A')} ({result.get('code')}): {signal_emoji} {signal}")
    
    # 筛选机会
    print("\n[2] 机会筛选...")
    opportunities = OpportunityFinder.find_opportunities(results)
    
    print(f"\n  建议买入 ({len(opportunities['buy_signals'])}):")
    for op in opportunities['buy_signals']:
        print(f"    🟢 {op['name']} ({op['code']}) - 评分: {op['score']}")
    
    print(f"\n  建议卖出 ({len(opportunities['sell_signals'])}):")
    for op in opportunities['sell_signals']:
        print(f"    🔴 {op['name']} ({op['code']}) - 评分: {op['score']}")
    
    # 保存结果
    output_file = Path(__file__).parent / "scan_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "scan_time": datetime.now().isoformat(),
            "results": results,
            "opportunities": opportunities
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存至: {output_file}")
    print("=" * 70)
    
    return opportunities


if __name__ == "__main__":
    run_scan()
