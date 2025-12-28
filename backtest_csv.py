#!/usr/bin/env python3
"""
暗号資産トレーディング戦略バックテストシステム（CSV版）
過去データCSVファイルを使用して検証
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from typing import List, Dict
import json

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class BacktestEngine:
    """バックテストエンジン"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.equity_curve = []
        
    def reset(self):
        self.capital = self.initial_capital
        self.position = 0
        self.trades = []
        self.equity_curve = []
    
    def execute_trade(self, price: float, amount: float, side: str, timestamp: datetime):
        if side == 'buy':
            cost = price * amount
            if cost <= self.capital:
                self.capital -= cost
                self.position += amount
                self.trades.append({
                    'timestamp': timestamp,
                    'side': 'buy',
                    'price': price,
                    'amount': amount,
                    'cost': cost
                })
        
        elif side == 'sell':
            if amount <= self.position:
                revenue = price * amount
                self.capital += revenue
                self.position -= amount
                self.trades.append({
                    'timestamp': timestamp,
                    'side': 'sell',
                    'price': price,
                    'amount': amount,
                    'revenue': revenue
                })
    
    def get_equity(self, current_price: float) -> float:
        return self.capital + (self.position * current_price)
    
    def record_equity(self, current_price: float, timestamp: datetime):
        equity = self.get_equity(current_price)
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity,
            'capital': self.capital,
            'position_value': self.position * current_price
        })


class GridTradingStrategy:
    """グリッドトレーディング戦略"""
    
    def __init__(self, lower_price: float, upper_price: float, grid_num: int, 
                 total_amount: float):
        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_num = grid_num
        self.total_amount = total_amount
        
        self.grid_step = (upper_price - lower_price) / grid_num
        self.grid_prices = [lower_price + (self.grid_step * i) 
                           for i in range(grid_num + 1)]
        
        self.grid_status = {price: 'empty' for price in self.grid_prices}
        self.last_price = None
        self.initialized = False
    
    def get_signals(self, current_price: float, timestamp: datetime) -> List[Dict]:
        signals = []
        
        if not self.initialized:
            # 初回：現在価格を基準にグリッドを配置
            for price in self.grid_prices:
                if price < current_price:
                    amount = (self.total_amount / 2) / (self.grid_num / 2) / price
                    signals.append({
                        'side': 'buy',
                        'price': current_price,  # 成行で買う
                        'amount': amount,
                        'timestamp': timestamp
                    })
                    self.grid_status[price] = 'filled'
            self.initialized = True
            self.last_price = current_price
            return signals
        
        # 価格が下がってグリッドを下抜けた場合
        for price in sorted(self.grid_prices):
            if (self.last_price > price >= current_price and 
                self.grid_status[price] == 'empty'):
                amount = (self.total_amount / 2) / (self.grid_num / 2) / price
                signals.append({
                    'side': 'buy',
                    'price': current_price,
                    'amount': amount,
                    'timestamp': timestamp
                })
                self.grid_status[price] = 'filled'
        
        # 価格が上がってグリッドを上抜けた場合
        for price in sorted(self.grid_prices, reverse=True):
            if (self.last_price < price <= current_price and 
                self.grid_status[price] == 'filled'):
                amount = (self.total_amount / 2) / (self.grid_num / 2) / price
                signals.append({
                    'side': 'sell',
                    'price': current_price,
                    'amount': amount,
                    'timestamp': timestamp
                })
                self.grid_status[price] = 'empty'
        
        self.last_price = current_price
        return signals


class PerformanceAnalyzer:
    """パフォーマンス分析"""
    
    @staticmethod
    def calculate_metrics(equity_curve: List[Dict], trades: List[Dict], 
                         initial_capital: float) -> Dict:
        if not equity_curve:
            return {}
        
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('timestamp', inplace=True)
        
        final_equity = equity_df['equity'].iloc[-1]
        total_return = (final_equity - initial_capital) / initial_capital * 100
        
        equity_df['daily_return'] = equity_df['equity'].pct_change()
        
        days = (equity_df.index[-1] - equity_df.index[0]).days
        years = days / 365.25
        cagr = (pow(final_equity / initial_capital, 1 / years) - 1) * 100 if years > 0 else 0
        
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
        max_drawdown = equity_df['drawdown'].min()
        
        daily_returns = equity_df['daily_return'].dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
        else:
            sharpe_ratio = 0
        
        # 勝率計算
        buy_trades = [t for t in trades if t['side'] == 'buy']
        sell_trades = [t for t in trades if t['side'] == 'sell']
        
        if len(buy_trades) > 0 and len(sell_trades) > 0:
            profits = []
            for sell in sell_trades:
                # 最も近い過去の買い注文を探す
                matching_buys = [b for b in buy_trades if b['timestamp'] < sell['timestamp']]
                if matching_buys:
                    buy = matching_buys[-1]
                    profit = (sell['price'] - buy['price']) / buy['price']
                    profits.append(profit)
            
            win_rate = len([p for p in profits if p > 0]) / len(profits) * 100 if profits else 0
        else:
            win_rate = 0
        
        trade_count = len(trades)
        
        return {
            '初期資本': f"{initial_capital:,.0f} USDT",
            '最終資産': f"{final_equity:,.0f} USDT",
            '純利益': f"{final_equity - initial_capital:,.0f} USDT",
            '総リターン': f"{total_return:.2f}%",
            '年率リターン(CAGR)': f"{cagr:.2f}%",
            '最大ドローダウン': f"{max_drawdown:.2f}%",
            'シャープレシオ': f"{sharpe_ratio:.2f}",
            '勝率': f"{win_rate:.2f}%",
            '取引回数': trade_count,
            'バックテスト期間': f"{days}日"
        }
    
    @staticmethod
    def plot_results(equity_curve: List[Dict], trades: List[Dict], price_data: pd.DataFrame,
                    strategy_name: str, save_path: str = None):
        equity_df = pd.DataFrame(equity_curve)
        equity_df.set_index('timestamp', inplace=True)
        
        fig, axes = plt.subplots(4, 1, figsize=(16, 12))
        
        # 1. 価格チャート
        axes[0].plot(price_data.index, price_data['close'], label='BTC Price', linewidth=1.5, color='blue')
        axes[0].set_title(f'{strategy_name} - Price Chart', fontsize=14, fontweight='bold')
        axes[0].set_ylabel('Price (USDT)', fontsize=12)
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        # 2. 資産推移
        axes[1].plot(equity_df.index, equity_df['equity'], label='Total Equity', linewidth=2, color='green')
        axes[1].axhline(y=equity_df['equity'].iloc[0], color='red', linestyle='--', label='Initial Capital')
        axes[1].set_title('Equity Curve', fontsize=14, fontweight='bold')
        axes[1].set_ylabel('Equity (USDT)', fontsize=12)
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        # 3. ドローダウン
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
        axes[2].fill_between(equity_df.index, equity_df['drawdown'], 0, 
                             color='red', alpha=0.3, label='Drawdown')
        axes[2].set_title('Drawdown', fontsize=14, fontweight='bold')
        axes[2].set_ylabel('Drawdown (%)', fontsize=12)
        axes[2].legend()
        axes[2].grid(True, alpha=0.3)
        
        # 4. 取引履歴
        trades_df = pd.DataFrame(trades)
        if not trades_df.empty:
            trades_df.set_index('timestamp', inplace=True)
            buy_trades = trades_df[trades_df['side'] == 'buy']
            sell_trades = trades_df[trades_df['side'] == 'sell']
            
            axes[3].scatter(buy_trades.index, buy_trades['price'], 
                           color='green', marker='^', s=50, label='Buy', alpha=0.6)
            axes[3].scatter(sell_trades.index, sell_trades['price'], 
                           color='red', marker='v', s=50, label='Sell', alpha=0.6)
            axes[3].set_title('Trade History', fontsize=14, fontweight='bold')
            axes[3].set_ylabel('Price (USDT)', fontsize=12)
            axes[3].set_xlabel('Date', fontsize=12)
            axes[3].legend()
            axes[3].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✓ グラフ保存: {save_path}")
        
        plt.close()


def load_csv_data(filepath: str) -> pd.DataFrame:
    """CSVデータ読み込み"""
    print(f"データ読み込み中: {filepath}")
    
    df = pd.DataFrame()
    df = pd.read_csv(filepath, header=None)
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                  'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
                  'taker_buy_quote', 'ignore']
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df.set_index('timestamp', inplace=True)
    
    print(f"✓ データ読み込み完了: {len(df)}件")
    print(f"  期間: {df.index[0]} ～ {df.index[-1]}")
    print(f"  価格レンジ: ${df['low'].min():,.0f} ～ ${df['high'].max():,.0f}")
    
    return df


def run_backtest(df: pd.DataFrame, strategy_params: Dict, 
                initial_capital: float = 10000) -> Dict:
    """バックテスト実行"""
    print(f"\n{'='*60}")
    print(f"バックテスト開始")
    print(f"{'='*60}")
    print(f"初期資本: ${initial_capital:,.0f}")
    print(f"グリッド数: {strategy_params['grid_num']}")
    print(f"価格レンジ: ${strategy_params['lower_price']:,.0f} ～ ${strategy_params['upper_price']:,.0f}")
    
    engine = BacktestEngine(initial_capital)
    strategy = GridTradingStrategy(
        lower_price=strategy_params['lower_price'],
        upper_price=strategy_params['upper_price'],
        grid_num=strategy_params['grid_num'],
        total_amount=initial_capital
    )
    
    print("\nバックテスト実行中...")
    for timestamp, row in df.iterrows():
        current_price = row['close']
        signals = strategy.get_signals(current_price, timestamp)
        
        for signal in signals:
            engine.execute_trade(
                price=signal['price'],
                amount=signal['amount'],
                side=signal['side'],
                timestamp=timestamp
            )
        
        engine.record_equity(current_price, timestamp)
    
    print("✓ バックテスト完了")
    
    metrics = PerformanceAnalyzer.calculate_metrics(
        engine.equity_curve,
        engine.trades,
        initial_capital
    )
    
    print("\n" + "="*60)
    print("バックテスト結果")
    print("="*60)
    for key, value in metrics.items():
        print(f"{key:20s}: {value}")
    print("="*60)
    
    strategy_name = f"Grid Trading ({strategy_params['grid_num']} grids)"
    PerformanceAnalyzer.plot_results(
        engine.equity_curve,
        engine.trades,
        df,
        strategy_name,
        save_path=f"backtest_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    )
    
    return {
        'metrics': metrics,
        'equity_curve': engine.equity_curve,
        'trades': engine.trades,
        'strategy_params': strategy_params
    }


def optimize_parameters(df: pd.DataFrame, initial_capital: float = 10000) -> pd.DataFrame:
    """パラメータ最適化"""
    print(f"\n{'='*60}")
    print(f"パラメータ最適化開始")
    print(f"{'='*60}")
    
    price_min = df['low'].min()
    price_max = df['high'].max()
    price_mean = df['close'].mean()
    price_range = price_max - price_min
    
    print(f"価格統計:")
    print(f"  最小: ${price_min:,.0f}")
    print(f"  最大: ${price_max:,.0f}")
    print(f"  平均: ${price_mean:,.0f}")
    print(f"  レンジ: ${price_range:,.0f}")
    
    grid_nums = [10, 15, 20, 25, 30]
    range_ratios = [0.7, 0.8, 0.9, 1.0]
    
    results = []
    total_tests = len(grid_nums) * len(range_ratios)
    current_test = 0
    
    for grid_num in grid_nums:
        for range_ratio in range_ratios:
            current_test += 1
            print(f"\n[{current_test}/{total_tests}] テスト中: グリッド数={grid_num}, レンジ比率={range_ratio}")
            
            lower_price = price_min + (price_range * (1 - range_ratio) / 2)
            upper_price = price_max - (price_range * (1 - range_ratio) / 2)
            
            strategy_params = {
                'lower_price': lower_price,
                'upper_price': upper_price,
                'grid_num': grid_num
            }
            
            engine = BacktestEngine(initial_capital)
            strategy = GridTradingStrategy(
                lower_price=lower_price,
                upper_price=upper_price,
                grid_num=grid_num,
                total_amount=initial_capital
            )
            
            for timestamp, row in df.iterrows():
                current_price = row['close']
                signals = strategy.get_signals(current_price, timestamp)
                
                for signal in signals:
                    engine.execute_trade(
                        price=signal['price'],
                        amount=signal['amount'],
                        side=signal['side'],
                        timestamp=timestamp
                    )
                
                engine.record_equity(current_price, timestamp)
            
            if engine.equity_curve:
                equity_df = pd.DataFrame(engine.equity_curve)
                final_equity = equity_df['equity'].iloc[-1]
                total_return = (final_equity - initial_capital) / initial_capital * 100
                
                equity_df['cummax'] = equity_df['equity'].cummax()
                equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
                max_drawdown = equity_df['drawdown'].min()
                
                results.append({
                    'grid_num': grid_num,
                    'range_ratio': range_ratio,
                    'lower_price': lower_price,
                    'upper_price': upper_price,
                    'total_return': total_return,
                    'max_drawdown': max_drawdown,
                    'trade_count': len(engine.trades),
                    'final_equity': final_equity
                })
                
                print(f"  リターン: {total_return:.2f}%, DD: {max_drawdown:.2f}%, 取引: {len(engine.trades)}回")
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('total_return', ascending=False)
    
    print("\n" + "="*60)
    print("最適化結果（上位10件）")
    print("="*60)
    print(results_df.head(10).to_string(index=False))
    
    results_df.to_csv('optimization_results.csv', index=False)
    print("\n✓ 結果保存: optimization_results.csv")
    
    return results_df


def main():
    """メイン関数"""
    print("="*60)
    print("暗号資産トレーディング戦略バックテストシステム")
    print("="*60)
    
    # データ読み込み
    df = load_csv_data('btc_2024_full.csv')
    
    # 初期資本
    initial_capital = 10000  # 10,000 USDT
    
    # パラメータ最適化
    print("\n[1] パラメータ最適化を実行")
    results_df = optimize_parameters(df, initial_capital)
    
    # 最適パラメータでバックテスト
    print("\n[2] 最適パラメータでバックテスト実行")
    best_params = results_df.iloc[0]
    strategy_params = {
        'lower_price': best_params['lower_price'],
        'upper_price': best_params['upper_price'],
        'grid_num': int(best_params['grid_num'])
    }
    
    result = run_backtest(df, strategy_params, initial_capital)
    
    # 結果サマリー保存
    summary = {
        'backtest_date': datetime.now().isoformat(),
        'data_period': f"{df.index[0]} to {df.index[-1]}",
        'initial_capital': initial_capital,
        'best_params': strategy_params,
        'metrics': result['metrics']
    }
    
    with open('backtest_summary.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print("\n✓ 全ての処理が完了しました")
    print("  - optimization_results.csv: 全パラメータの最適化結果")
    print("  - backtest_result_*.png: 詳細グラフ")
    print("  - backtest_summary.json: 結果サマリー")


if __name__ == "__main__":
    main()
