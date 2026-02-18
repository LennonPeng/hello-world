#!/usr/bin/env python3
"""
仓位管理与止损止盈模块
"""
from enum import Enum
from typing import Dict, Optional
from datetime import datetime


class PositionSize(Enum):
    """仓位大小"""
    FULL = 1.0      # 满仓
    THREE_QUARTERS = 0.75  # 75%仓位
    HALF = 0.5      # 半仓
    QUARTER = 0.25   # 25%仓位
    MINIMUM = 0.1    # 最小仓位


class RiskManager:
    """风险管理器"""
    
    def __init__(
        self,
        max_position_pct: float = 0.3,    # 单标的最大仓位占比
        max_loss_pct: float = -0.07,       # 最大止损线 -7%
        take_profit_pct: float = 0.15,     # 止盈线 +15%
        trailing_stop_pct: float = 0.05    # 追踪止损 -5%
    ):
        self.max_position_pct = max_position_pct  # 单标最高30%仓位
        self.max_loss_pct = max_loss_pct          # 止损 -7%
        self.take_profit_pct = take_profit_pct    # 止盈 +15%
        self.trailing_stop_pct = trailing_stop_pct  # 追踪止损
    
    def calculate_position_size(
        self,
        signal_strength: float,  # 信号强度 0-1
        market_regime: str,       # 市场状态
        account_balance: float    # 账户余额
    ) -> float:
        """
        计算建议仓位
        """
        # 基础仓位
        base_pct = 0.1  # 最小10%
        
        # 根据信号强度调整
        if signal_strength >= 0.8:
            base_pct = self.max_position_pct
        elif signal_strength >= 0.5:
            base_pct = self.max_position_pct * 0.75
        else:
            base_pct = self.max_position_pct * 0.5
        
        # 根据市场状态调整
        if market_regime == "mean_reversion":
            base_pct *= 0.7  # 震荡市降低仓位
        elif market_regime == "trend_down":
            base_pct *= 0.5  # 下跌趋势降低仓位
        
        # 计算金额
        position_value = account_balance * base_pct
        
        return min(position_value, account_balance * self.max_position_pct)
    
    def check_stop_loss(self, entry_price: float, current_price: float) -> bool:
        """
        检查是否触发止损
        """
        loss_pct = (current_price - entry_price) / entry_price
        return loss_pct <= self.max_loss_pct
    
    def check_take_profit(self, entry_price: float, current_price: float, highest_price: float) -> bool:
        """
        检查是否触发止盈
        """
        profit_pct = (current_price - entry_price) / entry_price
        
        # 止盈条件：达到止盈线 或 追踪止损
        if profit_pct >= self.take_profit_pct:
            # 触发止盈，检查追踪止损
            trailing_stop_price = highest_price * (1 - self.trailing_stop_pct)
            return current_price <= trailing_stop_price
        
        return False
    
    def should_add_position(
        self,
        current_position: float,
        signal_strength: float,
        current_price: float,
        avg_cost: float
    ) -> bool:
        """
        是否应该加仓
        """
        # 只有盈利且信号增强时才加仓
        if current_price <= avg_cost:
            return False
        
        profit_pct = (current_price - avg_cost) / avg_cost
        return profit_pct > 0.05 and signal_strength > 0.7
    
    def get_trade_recommendation(
        self,
        entry_price: float,
        current_price: float,
        highest_price: float,
        signal: str
    ) -> Dict:
        """
        获取交易建议
        """
        profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        
        # 检查各种条件
        trigger_stop_loss = self.check_stop_loss(entry_price, current_price)
        trigger_take_profit = self.check_take_profit(entry_price, current_price, highest_price)
        
        if signal == "SELL" or trigger_stop_loss:
            action = "SELL"
            reason = f"止损: {profit_pct*100:.1f}%" if trigger_stop_loss else "信号转空"
        elif trigger_take_profit:
            action = "SELL"
            reason = f"止盈/追踪止损: {profit_pct*100:.1f}%"
        elif signal == "BUY":
            action = "HOLD"
            reason = "持有，等待盈利"
        else:
            action = "HOLD"
            reason = "观望"
        
        return {
            "action": action,
            "reason": reason,
            "profit_pct": round(profit_pct * 100, 2),
            "stop_loss_price": round(entry_price * (1 + self.max_loss_pct), 2),
            "take_profit_price": round(entry_price * (1 + self.take_profit_pct), 2),
            "trailing_stop_price": round(highest_price * (1 - self.trailing_stop_pct), 2)
        }


# ============== 持仓管理 ==============
class Position:
    """持仓记录"""
    
    def __init__(
        self,
        code: str,
        name: str,
        quantity: float,
        avg_cost: float,
        entry_date: str
    ):
        self.code = code
        self.name = name
        self.quantity = quantity           # 数量
        self.avg_cost = avg_cost          # 平均成本
        self.entry_date = entry_date      # 建仓日期
        self.highest_price = avg_cost     # 最高价（用于追踪止损）
    
    def update_price(self, current_price: float):
        """更新当前价格"""
        if current_price > self.highest_price:
            self.highest_price = current_price
    
    def get_value(self, current_price: float) -> float:
        """当前市值"""
        return self.quantity * current_price
    
    def get_profit_pct(self, current_price: float) -> float:
        """盈亏比例"""
        return (current_price - self.avg_cost) / self.avg_cost


class Portfolio:
    """持仓组合"""
    
    def __init__(self, initial_balance: float = 100000):
        self.initial_balance = initial_balance
        self.cash = initial_balance
        self.positions: Dict[str, Position] = {}
        self.risk_manager = RiskManager()
    
    def buy(
        self,
        code: str,
        name: str,
        price: float,
        quantity: float
    ) -> bool:
        """买入"""
        cost = price * quantity
        if cost > self.cash:
            return False  # 资金不足
        
        if code in self.positions:
            # 加仓
            pos = self.positions[code]
            total_cost = pos.avg_cost * pos.quantity + price * quantity
            pos.quantity += quantity
            pos.avg_cost = total_cost / pos.quantity
        else:
            # 新建仓
            self.positions[code] = Position(
                code=code,
                name=name,
                quantity=quantity,
                avg_cost=price,
                entry_date=datetime.now().strftime("%Y-%m-%d")
            )
        
        self.cash -= cost
        return True
    
    def sell(self, code: str, price: float, quantity: float = None) -> float:
        """卖出"""
        if code not in self.positions:
            return 0
        
        pos = self.positions[code]
        
        # 默认全部卖出
        if quantity is None or quantity >= pos.quantity:
            quantity = pos.quantity
        
        proceeds = price * quantity
        self.cash += proceeds
        pos.quantity -= quantity
        
        # 删除空仓
        if pos.quantity <= 0:
            del self.positions[code]
        
        return proceeds
    
    def update_positions(self, market_data: Dict[str, float]):
        """更新持仓状态"""
        for code, price in market_data.items():
            if code in self.positions:
                self.positions[code].update_price(price)
    
    def get_portfolio_value(self, market_data: Dict[str, float]) -> float:
        """组合市值"""
        positions_value = sum(
            self.positions[code].get_value(price)
            for code, price in market_data.items()
            if code in self.positions
        )
        return self.cash + positions_value
    
    def check_risk(self, market_data: Dict[str, float]) -> Dict:
        """检查风险"""
        alerts = []
        
        for code, price in market_data.items():
            if code not in self.positions:
                continue
            
            pos = self.positions[code]
            recommendation = self.risk_manager.get_trade_recommendation(
                entry_price=pos.avg_cost,
                current_price=price,
                highest_price=pos.highest_price,
                signal="HOLD"  # 这里应该传入当前信号
            )
            
            if recommendation["action"] == "SELL":
                alerts.append({
                    "code": code,
                    "name": pos.name,
                    "action": recommendation["action"],
                    "reason": recommendation["reason"],
                    "profit_pct": recommendation["profit_pct"]
                })
        
        return {
            "total_value": self.get_portfolio_value(market_data),
            "cash": self.cash,
            "positions_count": len(self.positions),
            "alerts": alerts
        }


# ============== 测试 ==============
if __name__ == "__main__":
    # 测试仓位管理
    rm = RiskManager()
    
    # 测试计算仓位
    position = rm.calculate_position_size(
        signal_strength=0.8,
        market_regime="trend_up",
        account_balance=100000
    )
    print(f"建议仓位: {position:.2f} 元 ({position/100000*100:.1f}%)")
    
    # 测试止损止盈
    result = rm.get_trade_recommendation(
        entry_price=10.0,
        current_price=9.5,
        highest_price=12.0,
        signal="HOLD"
    )
    print(f"交易建议: {result}")
    
    # 测试组合
    portfolio = Portfolio(initial_balance=100000)
    portfolio.buy("600519", "贵州茅台", 1800.0, 10)
    print(f"买入后现金: {portfolio.cash}")
    print(f"持仓: {list(portfolio.positions.keys())}")
