#!/usr/bin/env python3
"""
三策略结合量化交易系统
- 趋势跟踪：均线金叉/死叉
- 均值回归：震荡市场低买高卖
- LLM 辅助：分析财报/新闻生成信号
"""
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List
import json
import os
import requests
from pathlib import Path

# 加载 .env 配置
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ.setdefault(key, val)

from tenacity import retry, stop_after_attempt, wait_exponential

# ============== 配置 ==============
class Config:
    # 均线参数
    SHORT_MA = 5    # 短期均线
    LONG_MA = 20    # 长期均线
    
    # 均值回归参数
    REVERSION_WINDOW = 20    # 滚动窗口
    REVERSION_STD = 2.0      # 标准差倍数
    
    # MiniMax LLM API 配置
    # 请设置环境变量 MINIMAX_API_KEY 或直接填入
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_MODEL = "MiniMax-M2.1"  # 可选: MiniMax-M2.1, MiniMax-M2.5
    MINIMAX_BASE_URL = "https://api.minimax.chat/v1"
    
    # 策略权重
    TREND_WEIGHT = 0.4
    REVERSION_WEIGHT = 0.3
    LLM_WEIGHT = 0.3


# ============== 信号枚举 ==============
class Signal(Enum):
    BUY = 1
    SELL = -1
    HOLD = 0


class MarketRegime(Enum):
    TREND_UP = "trend_up"       # 上升趋势
    TREND_DOWN = "trend_down"   # 下降趋势
    MEAN_REVERSION = "mean_reversion"  # 震荡/均值回归


# ============== 数据获取 ==============
class DataFetcher:
    """数据获取模块"""
    
    @staticmethod
    def get_stock_daily(symbol: str, days: int = 60) -> pd.DataFrame:
        """获取A股日线数据"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(
            symbol=symbol, 
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_change',
            '涨跌额': 'change', '换手率': 'turnover'
        })
        df['date'] = pd.to_datetime(df['date'])
        return df.tail(days)
    
    @staticmethod
    def get_etf_daily(symbol: str, days: int = 60) -> pd.DataFrame:
        """获取ETF日线数据"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d")
        
        df = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_change',
            '涨跌额': 'change', '换手率': 'turnover'
        })
        df['date'] = pd.to_datetime(df['date'])
        return df.tail(days)


# ============== 策略1: 趋势跟踪 ==============
class TrendStrategy:
    """均线金叉/死叉策略"""
    
    def __init__(self, short_ma: int = Config.SHORT_MA, long_ma: int = Config.LONG_MA):
        self.short_ma = short_ma
        self.long_ma = long_ma
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均线"""
        df = df.copy()
        df['ma_short'] = df['close'].rolling(window=self.short_ma).mean()
        df['ma_long'] = df['close'].rolling(window=self.long_ma).mean()
        
        # 金叉/死叉信号
        df['ma_cross'] = 0
        df.loc[df['ma_short'] > df['ma_long'], 'ma_cross'] = 1   # 金叉
        df.loc[df['ma_short'] < df['ma_long'], 'ma_cross'] = -1  # 死叉
        
        # 交叉变化检测
        df['ma_signal'] = 0
        df['ma_signal'] = df['ma_cross'].diff()
        df.loc[df['ma_signal'] > 0, 'ma_signal'] = 1   # 金叉形成
        df.loc[df['ma_signal'] < 0, 'ma_signal'] = -1  # 死叉形成
        
        return df
    
    def get_signal(self, df: pd.DataFrame) -> Signal:
        """获取当前信号"""
        df = self.calculate(df)
        
        if len(df) < self.long_ma:
            return Signal.HOLD
        
        last_row = df.iloc[-1]
        
        # 金叉买入
        if last_row['ma_signal'] == 1:
            return Signal.BUY
        # 死叉卖出
        elif last_row['ma_signal'] == -1:
            return Signal.SELL
        # 持有
        elif last_row['ma_cross'] == 1:
            return Signal.HOLD  # 继续持有
        else:
            return Signal.HOLD


# ============== 策略2: 均值回归 ==============
class MeanReversionStrategy:
    """均值回归策略"""
    
    def __init__(self, window: int = Config.REVERSION_WINDOW, std_multiplier: float = Config.REVERSION_STD):
        self.window = window
        self.std_multiplier = std_multiplier
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算均值回归指标"""
        df = df.copy()
        
        # 布林带
        df['ma'] = df['close'].rolling(window=self.window).mean()
        df['std'] = df['close'].rolling(window=self.window).std()
        df['upper'] = df['ma'] + self.std_multiplier * df['std']
        df['lower'] = df['ma'] - self.std_multiplier * df['std']
        
        # 位置百分比
        df['position'] = (df['close'] - df['lower']) / (df['upper'] - df['lower'])
        
        return df
    
    def get_signal(self, df: pd.DataFrame) -> Signal:
        """获取当前信号"""
        df = self.calculate(df)
        
        if len(df) < self.window:
            return Signal.HOLD
        
        last_row = df.iloc[-1]
        
        # 价格低于下轨 -> 买入
        if last_row['close'] < last_row['lower']:
            return Signal.BUY
        # 价格高于上轨 -> 卖出
        elif last_row['close'] > last_row['upper']:
            return Signal.SELL
        # 接近下轨 -> 买入
        elif last_row['position'] < 0.2:
            return Signal.BUY
        # 接近上轨 -> 卖出
        elif last_row['position'] > 0.8:
            return Signal.SELL
        else:
            return Signal.HOLD


# ============== 策略3: LLM 辅助 (MiniMax) ==============
class LLMStrategy:
    """LLM 分析辅助策略 - 基于 MiniMax API"""
    
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or Config.MINIMAX_API_KEY
        self.model = model or Config.MINIMAX_MODEL
        self.base_url = Config.MINIMAX_BASE_URL
    
    def _call_api(self, messages: List[Dict]) -> str:
        """调用 MiniMax API"""
        if not self.api_key:
            raise ValueError("未配置 MINIMAX_API_KEY")
        
        url = f"{self.base_url}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3  # 低温度，更确定性的输出
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content']
    
    def _parse_signal(self, text: str) -> tuple:
        """解析 LLM 返回的信号"""
        text = text.upper()
        
        if "BUY" in text and "SELL" not in text:
            return Signal.BUY, 0.7
        elif "SELL" in text:
            return Signal.SELL, 0.7
        else:
            return Signal.HOLD, 0.5
    
    def analyze_news(self, symbol: str, news_list: List[str]) -> Dict:
        """
        分析新闻/财报，生成交易信号
        """
        if not self.api_key:
            return {"signal": Signal.HOLD, "confidence": 0, "reason": "未配置 MINIMAX_API_KEY"}
        
        news_text = "\n".join([f"- {n}" for n in news_list])
        
        system_prompt = """你是一位专业的量化交易分析师。根据提供的新闻内容，输出短期交易建议。
要求：
1. 只输出 BUY、SELL 或 HOLD 其中一个
2. BUY = 买入/看多
3. SELL = 卖出/看空  
4. HOLD = 持有/观望
5. 同时给出置信度 (0-1)
格式：SIGNAL: BUY/SELL/HOLD, CONFIDENCE: 0.xx, REASON: 简短原因"""
        
        user_prompt = f"股票/ETF 代码: {symbol}\n新闻内容:\n{news_text}\n\n请分析并给出交易建议:"
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = self._call_api(messages)
            signal, confidence = self._parse_signal(response)
            
            return {
                "signal": signal,
                "confidence": confidence,
                "reason": response,
                "raw_response": response
            }
        except Exception as e:
            return {"signal": Signal.HOLD, "confidence": 0, "reason": f"API调用失败: {e}"}
    
    def analyze_technical(self, df: pd.DataFrame, symbol: str = "510050") -> Dict:
        """
        基于技术指标让 LLM 分析
        """
        if not self.api_key:
            return {"signal": Signal.HOLD, "confidence": 0, "reason": "未配置 MINIMAX_API_KEY"}
        
        # 提取关键指标
        latest = df.iloc[-1]
        prev5 = df.iloc[-6] if len(df) >= 6 else latest
        
        # 构建技术分析上下文
        ma_short = latest.get('ma_short', latest['close'])
        ma_long = latest.get('ma_long', latest['close'])
        
        stats = {
            "symbol": symbol,
            "close": round(latest['close'], 3),
            "pct_change": round(latest.get('pct_change', 0), 2),
            "volume": int(latest.get('volume', 0)),
            "ma5": round(ma_short, 3),
            "ma20": round(ma_long, 3),
            "upper": round(latest.get('upper', 0), 3),
            "lower": round(latest.get('lower', 0), 3),
            "position": round(latest.get('position', 0.5), 2),
        }
        
        system_prompt = """你是一位专业的量化交易分析师。根据提供的技术指标，分析短期走势并给出交易建议。
要求：
1. 只输出 BUY、SELL 或 HOLD 其中一个
2. 结合均线交叉、布林带位置、涨跌幅综合判断
3. 输出格式：SIGNAL: BUY/SELL/HOLD, CONFIDENCE: 0.xx, REASON: 简短原因"""
        
        user_prompt = f"""ETF 代码: {symbol}
技术指标:
- 当前收盘价: {stats['close']}
- 涨跌幅: {stats['pct_change']}%
- 成交量: {stats['volume']}
- MA5: {stats['ma5']}
- MA20: {stats['ma20']}
- 布林上轨: {stats['upper']}
- 布林下轨: {stats['lower']}
- 布林位置: {stats['position']}

请分析并给出交易建议:"""
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = self._call_api(messages)
            signal, confidence = self._parse_signal(response)
            
            return {
                "signal": signal,
                "confidence": confidence,
                "reason": response,
                "stats": stats,
                "raw_response": response
            }
        except Exception as e:
            return {"signal": Signal.HOLD, "confidence": 0, "reason": f"API调用失败: {e}", "stats": stats}


# ============== 市场判断 ==============
class MarketRegimeDetector:
    """市场状态检测"""
    
    @staticmethod
    def detect(df: pd.DataFrame) -> MarketRegime:
        """检测市场状态"""
        if len(df) < 20:
            return MarketRegime.MEAN_REVERSION
        
        # 计算波动率
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        volatility = df['returns'].rolling(20).std()
        
        # 计算趋势强度
        ma20 = df['close'].rolling(20).mean()
        ma60 = df['close'].rolling(60).mean()
        
        current_vol = volatility.iloc[-1]
        avg_vol = volatility.mean()
        
        # 高波动 + 无明显趋势 -> 震荡/均值回归
        if current_vol > avg_vol * 1.2:
            return MarketRegime.MEAN_REVERSION
        
        # 明显趋势
        if ma20.iloc[-1] > ma60.iloc[-1]:
            return MarketRegime.TREND_UP
        else:
            return MarketRegime.TREND_DOWN


# ============== 策略组合引擎 ==============
class StrategyEnsemble:
    """多策略组合引擎"""
    
    def __init__(self):
        self.trend_strategy = TrendStrategy()
        self.reversion_strategy = MeanReversionStrategy()
        self.llm_strategy = LLMStrategy()
        self.market_detector = MarketRegimeDetector()
    
    def get_ensemble_signal(self, df: pd.DataFrame, market_regime: MarketRegime = None) -> Dict:
        """获取组合信号"""
        
        # 自动检测市场状态
        if market_regime is None:
            market_regime = self.market_detector.detect(df)
        
        # 获取各策略信号
        trend_signal = self.trend_strategy.get_signal(df)
        reversion_signal = self.reversion_strategy.get_signal(df)
        # llm_signal = self.llm_strategy.analyze_technical(df)  # TODO: 启用 LLM
        
        # 根据市场状态调整权重
        if market_regime == MarketRegime.TREND_UP:
            weights = {"trend": 0.5, "reversion": 0.2, "llm": 0.3}
        elif market_regime == MarketRegime.TREND_DOWN:
            weights = {"trend": 0.5, "reversion": 0.1, "llm": 0.4}
        else:  # 均值回归
            weights = {"trend": 0.2, "reversion": 0.5, "llm": 0.3}
        
        # 获取 LLM 信号 (可选，API 未配置时跳过)
        llm_result = {"signal": Signal.HOLD, "confidence": 0, "reason": "未配置LLM"}
        if self.llm_strategy.api_key:
            try:
                llm_result = self.llm_strategy.analyze_technical(df)
            except Exception as e:
                llm_result = {"signal": Signal.HOLD, "confidence": 0, "reason": f"LLM错误: {e}"}
        
        llm_signal = llm_result.get("signal", Signal.HOLD)
        
        # 加权计算
        score = (
            trend_signal.value * weights["trend"] +
            reversion_signal.value * weights["reversion"] +
            llm_signal.value * weights["llm"]
        )
        
        # 阈值判断
        if score > 0.3:
            final_signal = Signal.BUY
        elif score < -0.3:
            final_signal = Signal.SELL
        else:
            final_signal = Signal.HOLD
        
        return {
            "signal": final_signal,
            "score": score,
            "market_regime": market_regime.value,
            "trend_signal": trend_signal.name,
            "reversion_signal": reversion_signal.name,
            "llm_signal": llm_signal.name,
            "llm_reason": llm_result.get("reason", ""),
            "weights": weights
        }


# ============== 回测测试 ==============
def backtest():
    """简单回测演示"""
    print("=" * 60)
    print("三策略结合系统 - 回测演示")
    print("=" * 60)
    
    # 获取数据
    print("\n[1] 获取 ETF 数据...")
    df = DataFetcher.get_etf_daily("510050", days=120)
    print(f"    获取 {len(df)} 条数据")
    
    # 初始化引擎
    engine = StrategyEnsemble()
    
    # 简单回测
    print("\n[2] 运行回测...")
    df = engine.trend_strategy.calculate(df)
    df = engine.reversion_strategy.calculate(df)
    
    signals = []
    for i in range(60, len(df)):
        subset = df.iloc[:i+1]
        result = engine.get_ensemble_signal(subset)
        signals.append(result['signal'].name)
    
    df_result = df.iloc[60:].copy()
    df_result['signal'] = signals
    
    # 统计
    buys = (df_result['signal'] == 'BUY').sum()
    sells = (df_result['signal'] == 'SELL').sum()
    holds = (df_result['signal'] == 'HOLD').sum()
    
    print(f"\n[3] 回测结果统计:")
    print(f"    买入信号: {buys}")
    print(f"    卖出信号: {sells}")
    print(f"    持有信号: {holds}")
    
    print("\n" + "=" * 60)
    print("最近5个交易日信号:")
    print(df_result[['date', 'close', 'signal']].tail(5).to_string(index=False))
    print("=" * 60)


if __name__ == "__main__":
    backtest()
