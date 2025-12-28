#!/usr/bin/env python3
"""
高度なトレーディング戦略の実装
- グリッドトレーディング（改良版）
- ペアトレーディング
- モメンタム戦略
- 平均回帰戦略
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple


class ImprovedGridStrategy:
    """改良版グリッドトレーディング戦略
    
    改善点：
    - 動的グリッド調整
    - ボラティリティベースのポジションサイズ
    - ストップロス実装
    """
    
    def __init__(self, initial_capital: float, grid_num: int = 15, 
                 volatility_window: int = 30, stop_loss_pct: float = 15.0):
        self.initial_capital = initial_capital
        self.grid_num = grid_num
        self.volatility_window = volatility_window
        self.stop_loss_pct = stop_loss_pct
        
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.grid_prices = []
        self.grid_status = {}
        self.last_price = None
        self.entry_price = None
        
    def calculate_dynamic_range(self, price_history: pd.Series) -> Tuple[float, float]:
        """ボラティリティベースの動的レンジ計算"""
        current_price = price_history.iloc[-1]
        volatility = price_history.pct_change().std() * np.sqrt(365)
        
        # ボラティリティに応じてレンジを調整
        range_pct = min(0.3, max(0.15, volatility))  # 15%～30%
        
        lower_price = current_price * (1 - range_pct)
        upper_price = current_price * (1 + range_pct)
        
        return lower_price, upper_price
    
    def calculate_position_size(self, price_history: pd.Series) -> float:
        """ボラティリティベースのポジションサイズ計算"""
        volatility = price_history.pct_change().std()
        
        # ボラティリティが高い時はポジションを小さく
        base_size = self.capital * 0.5
        volatility_adj = 1 / (1 + volatility * 10)
        
        return base_size * volatility_adj
    
    def check_stop_loss(self, current_price: float) -> bool:
        """ストップロスチェック"""
        if self.entry_price is None or self.position == 0:
            return False
        
        loss_pct = (current_price - self.entry_price) / self.entry_price * 100
        
        if loss_pct < -self.stop_loss_pct:
            return True
        
        return False
    
    def get_signals(self, price_history: pd.Series, timestamp: pd.Timestamp) -> List[Dict]:
        """取引シグナル生成"""
        current_price = price_history.iloc[-1]
        signals = []
        
        # ストップロスチェック
        if self.check_stop_loss(current_price):
            if self.position > 0:
                signals.append({
                    'side': 'sell',
                    'price': current_price,
                    'amount': self.position,
                    'timestamp': timestamp,
                    'reason': 'stop_loss'
                })
                self.position = 0
                self.entry_price = None
            return signals
        
        # 動的レンジ計算
        if len(price_history) >= self.volatility_window:
            lower_price, upper_price = self.calculate_dynamic_range(
                price_history[-self.volatility_window:]
            )
            
            # グリッド再計算
            grid_step = (upper_price - lower_price) / self.grid_num
            self.grid_prices = [lower_price + (grid_step * i) 
                               for i in range(self.grid_num + 1)]
            
            # ポジションサイズ計算
            position_size = self.calculate_position_size(
                price_history[-self.volatility_window:]
            )
            
            # グリッド取引ロジック
            if self.last_price is not None:
                for price in self.grid_prices:
                    # 価格が下がってグリッドを下抜け → 買い
                    if self.last_price > price >= current_price:
                        if self.capital > 0:
                            amount = min(position_size / self.grid_num / current_price, 
                                       self.capital / current_price * 0.9)
                            if amount > 0:
                                signals.append({
                                    'side': 'buy',
                                    'price': current_price,
                                    'amount': amount,
                                    'timestamp': timestamp,
                                    'reason': 'grid_buy'
                                })
                                if self.entry_price is None:
                                    self.entry_price = current_price
                    
                    # 価格が上がってグリッドを上抜け → 売り
                    elif self.last_price < price <= current_price:
                        if self.position > 0:
                            amount = min(self.position / (self.grid_num / 2), 
                                       self.position * 0.9)
                            if amount > 0:
                                signals.append({
                                    'side': 'sell',
                                    'price': current_price,
                                    'amount': amount,
                                    'timestamp': timestamp,
                                    'reason': 'grid_sell'
                                })
        
        self.last_price = current_price
        return signals
    
    def execute_trade(self, signal: Dict):
        """取引実行"""
        if signal['side'] == 'buy':
            cost = signal['price'] * signal['amount']
            if cost <= self.capital:
                self.capital -= cost
                self.position += signal['amount']
                self.trades.append(signal)
        
        elif signal['side'] == 'sell':
            if signal['amount'] <= self.position:
                revenue = signal['price'] * signal['amount']
                self.capital += revenue
                self.position -= signal['amount']
                self.trades.append(signal)
                
                if self.position == 0:
                    self.entry_price = None


class MomentumStrategy:
    """モメンタム戦略
    
    価格が一定期間上昇し続けたら買い、下落し続けたら売り
    """
    
    def __init__(self, initial_capital: float, lookback: int = 20, 
                 threshold: float = 0.02):
        self.initial_capital = initial_capital
        self.lookback = lookback
        self.threshold = threshold
        
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.in_position = False
    
    def calculate_momentum(self, price_history: pd.Series) -> float:
        """モメンタム計算"""
        if len(price_history) < self.lookback:
            return 0
        
        returns = price_history.pct_change(self.lookback).iloc[-1]
        return returns
    
    def get_signals(self, price_history: pd.Series, timestamp: pd.Timestamp) -> List[Dict]:
        """取引シグナル生成"""
        signals = []
        
        if len(price_history) < self.lookback:
            return signals
        
        current_price = price_history.iloc[-1]
        momentum = self.calculate_momentum(price_history)
        
        # 強い上昇モメンタム → 買い
        if momentum > self.threshold and not self.in_position:
            amount = (self.capital * 0.95) / current_price
            if amount > 0:
                signals.append({
                    'side': 'buy',
                    'price': current_price,
                    'amount': amount,
                    'timestamp': timestamp,
                    'reason': f'momentum_up_{momentum:.2%}'
                })
                self.in_position = True
        
        # 強い下落モメンタム → 売り
        elif momentum < -self.threshold and self.in_position:
            if self.position > 0:
                signals.append({
                    'side': 'sell',
                    'price': current_price,
                    'amount': self.position,
                    'timestamp': timestamp,
                    'reason': f'momentum_down_{momentum:.2%}'
                })
                self.in_position = False
        
        return signals
    
    def execute_trade(self, signal: Dict):
        """取引実行"""
        if signal['side'] == 'buy':
            cost = signal['price'] * signal['amount']
            if cost <= self.capital:
                self.capital -= cost
                self.position += signal['amount']
                self.trades.append(signal)
        
        elif signal['side'] == 'sell':
            if signal['amount'] <= self.position:
                revenue = signal['price'] * signal['amount']
                self.capital += revenue
                self.position -= signal['amount']
                self.trades.append(signal)


class MeanReversionStrategy:
    """平均回帰戦略
    
    価格が移動平均から大きく乖離したら逆張り
    """
    
    def __init__(self, initial_capital: float, ma_period: int = 20, 
                 std_threshold: float = 2.0):
        self.initial_capital = initial_capital
        self.ma_period = ma_period
        self.std_threshold = std_threshold
        
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.in_position = False
    
    def calculate_z_score(self, price_history: pd.Series) -> float:
        """Zスコア計算"""
        if len(price_history) < self.ma_period:
            return 0
        
        ma = price_history.rolling(self.ma_period).mean().iloc[-1]
        std = price_history.rolling(self.ma_period).std().iloc[-1]
        current_price = price_history.iloc[-1]
        
        if std == 0:
            return 0
        
        z_score = (current_price - ma) / std
        return z_score
    
    def get_signals(self, price_history: pd.Series, timestamp: pd.Timestamp) -> List[Dict]:
        """取引シグナル生成"""
        signals = []
        
        if len(price_history) < self.ma_period:
            return signals
        
        current_price = price_history.iloc[-1]
        z_score = self.calculate_z_score(price_history)
        
        # 価格が平均より大きく下 → 買い（反発期待）
        if z_score < -self.std_threshold and not self.in_position:
            amount = (self.capital * 0.95) / current_price
            if amount > 0:
                signals.append({
                    'side': 'buy',
                    'price': current_price,
                    'amount': amount,
                    'timestamp': timestamp,
                    'reason': f'oversold_z={z_score:.2f}'
                })
                self.in_position = True
        
        # 価格が平均に回帰 → 売り
        elif z_score > -0.5 and self.in_position:
            if self.position > 0:
                signals.append({
                    'side': 'sell',
                    'price': current_price,
                    'amount': self.position,
                    'timestamp': timestamp,
                    'reason': f'mean_revert_z={z_score:.2f}'
                })
                self.in_position = False
        
        # 価格が平均より大きく上 → ショート（暗号資産では実装困難）
        # ここでは省略
        
        return signals
    
    def execute_trade(self, signal: Dict):
        """取引実行"""
        if signal['side'] == 'buy':
            cost = signal['price'] * signal['amount']
            if cost <= self.capital:
                self.capital -= cost
                self.position += signal['amount']
                self.trades.append(signal)
        
        elif signal['side'] == 'sell':
            if signal['amount'] <= self.position:
                revenue = signal['price'] * signal['amount']
                self.capital += revenue
                self.position -= signal['amount']
                self.trades.append(signal)


def run_strategy_comparison(df: pd.DataFrame, initial_capital: float = 10000):
    """複数戦略の比較実行"""
    print(f"\n{'='*60}")
    print(f"複数戦略比較バックテスト")
    print(f"{'='*60}")
    
    strategies = {
        '改良版グリッド': ImprovedGridStrategy(initial_capital),
        'モメンタム': MomentumStrategy(initial_capital),
        '平均回帰': MeanReversionStrategy(initial_capital)
    }
    
    results = {}
    
    for name, strategy in strategies.items():
        print(f"\n[{name}戦略] 実行中...")
        
        equity_curve = []
        
        for i in range(len(df)):
            timestamp = df.index[i]
            price_history = df['close'].iloc[:i+1]
            current_price = price_history.iloc[-1]
            
            # シグナル取得
            signals = strategy.get_signals(price_history, timestamp)
            
            # 取引実行
            for signal in signals:
                strategy.execute_trade(signal)
            
            # 資産記録
            equity = strategy.capital + (strategy.position * current_price)
            equity_curve.append({
                'timestamp': timestamp,
                'equity': equity
            })
        
        # 結果計算
        equity_df = pd.DataFrame(equity_curve)
        final_equity = equity_df['equity'].iloc[-1]
        total_return = (final_equity - initial_capital) / initial_capital * 100
        
        results[name] = {
            'final_equity': final_equity,
            'total_return': total_return,
            'trade_count': len(strategy.trades),
            'equity_curve': equity_curve
        }
        
        print(f"  最終資産: ${final_equity:,.0f}")
        print(f"  リターン: {total_return:.2f}%")
        print(f"  取引回数: {len(strategy.trades)}回")
    
    # 比較表示
    print(f"\n{'='*60}")
    print(f"戦略比較結果")
    print(f"{'='*60}")
    
    comparison_df = pd.DataFrame({
        name: {
            '最終資産': f"${result['final_equity']:,.0f}",
            'リターン': f"{result['total_return']:.2f}%",
            '取引回数': result['trade_count']
        }
        for name, result in results.items()
    }).T
    
    print(comparison_df)
    
    return results


if __name__ == "__main__":
    # テスト実行
    import sys
    sys.path.append('/home/ubuntu')
    from backtest_csv import load_csv_data
    
    df = load_csv_data('btc_2024_full.csv')
    results = run_strategy_comparison(df, initial_capital=10000)
