#!/usr/bin/env python3
"""
モメンタムトレーディングBot（本番用）

使い方:
1. momentum_config.jsonを編集してAPIキーを設定
2. python3 momentum_bot_production.py

機能:
- 20日間のモメンタム計算
- 自動売買
- ストップロス
- ログ記録
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
import json
import os

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('momentum_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MomentumBot:
    """モメンタムトレーディングBot（本番用）"""
    
    def __init__(self, config):
        self.config = config
        self.exchange = self._init_exchange()
        self.symbol = config['symbol']
        self.lookback = config['lookback']
        self.threshold = config['threshold']
        self.stop_loss_pct = config['stop_loss_pct']
        
        self.in_position = False
        self.entry_price = None
        self.position_size = 0
        
        # 取引履歴
        self.trades = []
        
        logger.info(f"Bot初期化完了: {self.symbol}")
        logger.info(f"ルックバック: {self.lookback}日")
        logger.info(f"閾値: {self.threshold*100}%")
        logger.info(f"ストップロス: {self.stop_loss_pct}%")
    
    def _init_exchange(self):
        """取引所初期化"""
        exchange_id = self.config['exchange']
        exchange_class = getattr(ccxt, exchange_id)
        
        exchange = exchange_class({
            'apiKey': self.config['api_key'],
            'secret': self.config['api_secret'],
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        # 接続テスト
        try:
            balance = exchange.fetch_balance()
            logger.info(f"取引所接続成功: {exchange_id}")
            logger.info(f"USDT残高: ${balance['USDT']['free']:,.2f}")
            if 'BTC' in balance:
                logger.info(f"BTC残高: {balance['BTC']['free']:.6f}")
        except Exception as e:
            logger.error(f"取引所接続エラー: {e}")
            raise
        
        return exchange
    
    def get_price_history(self):
        """過去価格データ取得"""
        try:
            # 1日足で取得（lookback + 余裕）
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol,
                '1d',
                limit=self.lookback + 10
            )
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df['close']
        
        except Exception as e:
            logger.error(f"価格データ取得エラー: {e}")
            raise
    
    def calculate_momentum(self, price_history):
        """モメンタム計算"""
        if len(price_history) < self.lookback:
            return 0
        
        returns = price_history.pct_change(self.lookback).iloc[-1]
        return returns
    
    def check_stop_loss(self, current_price):
        """ストップロスチェック"""
        if not self.in_position or self.entry_price is None:
            return False
        
        loss_pct = (current_price - self.entry_price) / self.entry_price * 100
        
        if loss_pct < -self.stop_loss_pct:
            logger.warning(f"⚠️ ストップロス発動: {loss_pct:.2f}%")
            return True
        
        return False
    
    def execute_buy(self, current_price):
        """買い注文実行"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance['USDT']['free']
            
            if usdt_balance < 10:
                logger.warning(f"残高不足: ${usdt_balance:.2f}")
                return False
            
            # 95%を使用（手数料分を残す）
            amount_usdt = usdt_balance * 0.95
            amount_btc = amount_usdt / current_price
            
            # 最小注文量チェック
            market = self.exchange.market(self.symbol)
            min_amount = market['limits']['amount']['min']
            
            if amount_btc < min_amount:
                logger.warning(f"注文量不足: {amount_btc:.6f} < {min_amount}")
                return False
            
            # 成行買い注文
            logger.info(f"📈 買い注文実行中...")
            order = self.exchange.create_market_buy_order(
                self.symbol,
                amount_btc
            )
            
            self.in_position = True
            self.entry_price = current_price
            self.position_size = amount_btc
            
            trade = {
                'timestamp': datetime.now().isoformat(),
                'side': 'buy',
                'price': current_price,
                'amount': amount_btc,
                'cost': amount_usdt
            }
            self.trades.append(trade)
            self._save_trades()
            
            logger.info(f"✅ 買い注文完了: {amount_btc:.6f} BTC @ ${current_price:,.0f}")
            logger.info(f"   投資額: ${amount_usdt:,.0f}")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ 買い注文エラー: {e}")
            return False
    
    def execute_sell(self, current_price):
        """売り注文実行"""
        try:
            balance = self.exchange.fetch_balance()
            btc_balance = balance['BTC']['free']
            
            if btc_balance == 0:
                logger.warning("売却可能なBTCがありません")
                return False
            
            # 成行売り注文
            logger.info(f"📉 売り注文実行中...")
            order = self.exchange.create_market_sell_order(
                self.symbol,
                btc_balance
            )
            
            revenue = btc_balance * current_price
            profit_pct = (current_price - self.entry_price) / self.entry_price * 100 if self.entry_price else 0
            profit_usdt = (current_price - self.entry_price) * btc_balance if self.entry_price else 0
            
            trade = {
                'timestamp': datetime.now().isoformat(),
                'side': 'sell',
                'price': current_price,
                'amount': btc_balance,
                'revenue': revenue,
                'profit_pct': profit_pct,
                'profit_usdt': profit_usdt
            }
            self.trades.append(trade)
            self._save_trades()
            
            self.in_position = False
            self.entry_price = None
            self.position_size = 0
            
            logger.info(f"✅ 売り注文完了: {btc_balance:.6f} BTC @ ${current_price:,.0f}")
            logger.info(f"   収益: ${revenue:,.0f}")
            logger.info(f"   利益: ${profit_usdt:,.0f} ({profit_pct:+.2f}%)")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ 売り注文エラー: {e}")
            return False
    
    def _save_trades(self):
        """取引履歴保存"""
        try:
            with open('trades_history.json', 'w') as f:
                json.dump(self.trades, f, indent=2)
        except Exception as e:
            logger.error(f"取引履歴保存エラー: {e}")
    
    def get_status(self):
        """現在のステータス取得"""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance['USDT']['free']
            btc = balance['BTC']['free'] if 'BTC' in balance else 0
            
            # 現在価格取得
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            total_value = usdt + (btc * current_price)
            
            status = {
                'timestamp': datetime.now().isoformat(),
                'usdt_balance': usdt,
                'btc_balance': btc,
                'btc_price': current_price,
                'total_value': total_value,
                'in_position': self.in_position,
                'entry_price': self.entry_price,
                'unrealized_pnl_pct': (current_price - self.entry_price) / self.entry_price * 100 if self.entry_price else 0
            }
            
            return status
        
        except Exception as e:
            logger.error(f"ステータス取得エラー: {e}")
            return None
    
    def print_status(self):
        """ステータス表示"""
        status = self.get_status()
        if status:
            logger.info("=" * 60)
            logger.info("現在のステータス")
            logger.info("=" * 60)
            logger.info(f"USDT残高: ${status['usdt_balance']:,.2f}")
            logger.info(f"BTC残高: {status['btc_balance']:.6f}")
            logger.info(f"BTC価格: ${status['btc_price']:,.0f}")
            logger.info(f"総資産: ${status['total_value']:,.2f}")
            logger.info(f"ポジション: {'保有中' if status['in_position'] else 'なし'}")
            if status['in_position']:
                logger.info(f"エントリー価格: ${status['entry_price']:,.0f}")
                logger.info(f"含み損益: {status['unrealized_pnl_pct']:+.2f}%")
            logger.info("=" * 60)
    
    def run(self, check_interval=3600):
        """Bot実行
        
        Args:
            check_interval: チェック間隔（秒）デフォルト1時間
        """
        logger.info("=" * 60)
        logger.info("🚀 モメンタムBot 起動")
        logger.info("=" * 60)
        
        self.print_status()
        
        iteration = 0
        
        while True:
            try:
                iteration += 1
                logger.info(f"\n--- チェック #{iteration} ---")
                
                # 価格データ取得
                price_history = self.get_price_history()
                current_price = price_history.iloc[-1]
                
                logger.info(f"現在価格: ${current_price:,.0f}")
                
                # ストップロスチェック
                if self.check_stop_loss(current_price):
                    self.execute_sell(current_price)
                    time.sleep(check_interval)
                    continue
                
                # モメンタム計算
                momentum = self.calculate_momentum(price_history)
                logger.info(f"モメンタム({self.lookback}日): {momentum:+.2%}")
                
                # シグナル判定
                if momentum > self.threshold and not self.in_position:
                    logger.info(f"🔔 買いシグナル発生 (モメンタム: {momentum:+.2%} > {self.threshold:+.2%})")
                    self.execute_buy(current_price)
                
                elif momentum < -self.threshold and self.in_position:
                    logger.info(f"🔔 売りシグナル発生 (モメンタム: {momentum:+.2%} < {-self.threshold:+.2%})")
                    self.execute_sell(current_price)
                
                else:
                    logger.info("シグナルなし")
                
                # ステータス表示
                if iteration % 6 == 0:  # 6時間ごと
                    self.print_status()
                
                # 待機
                logger.info(f"次のチェックまで {check_interval//60} 分待機...")
                time.sleep(check_interval)
            
            except KeyboardInterrupt:
                logger.info("\n⏹️ ユーザーによる停止")
                self.print_status()
                break
            
            except Exception as e:
                logger.error(f"❌ 実行エラー: {e}")
                logger.info(f"{check_interval//60} 分後に再試行...")
                time.sleep(check_interval)
        
        logger.info("=" * 60)
        logger.info("🛑 Bot停止")
        logger.info("=" * 60)


def main():
    """メイン関数"""
    config_file = 'momentum_config.json'
    
    if not os.path.exists(config_file):
        logger.error(f"設定ファイルが見つかりません: {config_file}")
        logger.info("momentum_config.json を作成してください")
        return
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        bot = MomentumBot(config)
        
        # 1時間ごとにチェック
        bot.run(check_interval=3600)
    
    except Exception as e:
        logger.error(f"Bot起動エラー: {e}")


if __name__ == "__main__":
    main()
