#!/usr/bin/env python3
"""
Momentum Trading Bot for BTC/JPY
Binance Japan対応版
"""
import ccxt
import pandas as pd
import time
import json
from datetime import datetime
import logging

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('momentum_bot.log'),
        logging.StreamHandler()
    ]
)

class MomentumBotJPY:
    def __init__(self, config):
        """
        モメンタムBot初期化
        
        Args:
            config: 設定辞書
        """
        self.exchange = ccxt.binance({
            'apiKey': config['api_key'],
            'secret': config['api_secret'],
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            }
        })
        
        self.symbol = config['symbol']  # BTC/JPY
        self.lookback = config['lookback']  # モメンタム計算期間
        self.threshold = config['threshold']  # 売買閾値
        self.stop_loss_pct = config['stop_loss_pct']  # ストップロス%
        
        self.in_position = False  # ポジション保有フラグ
        self.entry_price = None  # エントリー価格
        
        logging.info(f"Bot初期化完了: {self.symbol}")
        logging.info(f"ルックバック: {self.lookback}日")
        logging.info(f"閾値: {self.threshold*100}%")
        logging.info(f"ストップロス: {self.stop_loss_pct}%")
    
    def get_price_history(self):
        """
        過去価格データを取得
        
        Returns:
            pandas.Series: 終値の時系列データ
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol, 
                '1d', 
                limit=self.lookback + 10
            )
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            return df['close']
        except Exception as e:
            logging.error(f"価格データ取得エラー: {e}")
            return None
    
    def calculate_momentum(self, prices):
        """
        モメンタムを計算
        
        Args:
            prices: 価格の時系列データ
            
        Returns:
            float: モメンタム値（リターン率）
        """
        if len(prices) < self.lookback:
            return 0
        return prices.pct_change(self.lookback).iloc[-1]
    
    def check_stop_loss(self, current_price):
        """
        ストップロス判定
        
        Args:
            current_price: 現在価格
            
        Returns:
            bool: ストップロスに該当するか
        """
        if not self.in_position or self.entry_price is None:
            return False
        
        loss_pct = (current_price - self.entry_price) / self.entry_price * 100
        return loss_pct < -self.stop_loss_pct
    
    def get_balance(self):
        """
        残高を取得
        
        Returns:
            tuple: (JPY残高, BTC残高)
        """
        try:
            balance = self.exchange.fetch_balance()
            jpy = balance['JPY']['free'] if 'JPY' in balance else 0
            btc = balance['BTC']['free'] if 'BTC' in balance else 0
            return jpy, btc
        except Exception as e:
            logging.error(f"残高取得エラー: {e}")
            return 0, 0
    
    def execute_buy(self, current_price):
        """
        買い注文を実行
        
        Args:
            current_price: 現在価格
            
        Returns:
            bool: 注文成功したか
        """
        try:
            jpy, btc = self.get_balance()
            
            if jpy < 1000:  # 最低1,000円
                logging.warning(f"残高不足: ¥{jpy:,.0f}")
                return False
            
            # 95%の資金を使用（手数料考慮）
            amount_btc = (jpy * 0.95) / current_price
            
            # 最小注文量チェック（Binance Japanは0.0001 BTC）
            if amount_btc < 0.0001:
                logging.warning(f"注文量が最小値未満: {amount_btc:.6f} BTC")
                return False
            
            order = self.exchange.create_market_buy_order(self.symbol, amount_btc)
            
            self.in_position = True
            self.entry_price = current_price
            
            logging.info(f"✅ 買い: {amount_btc:.6f} BTC @ ¥{current_price:,.0f}")
            logging.info(f"注文ID: {order['id']}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ 買いエラー: {e}")
            return False
    
    def execute_sell(self, current_price):
        """
        売り注文を実行
        
        Args:
            current_price: 現在価格
            
        Returns:
            bool: 注文成功したか
        """
        try:
            jpy, btc = self.get_balance()
            
            if btc < 0.0001:  # 最小注文量
                logging.warning(f"BTC残高不足: {btc:.6f} BTC")
                return False
            
            order = self.exchange.create_market_sell_order(self.symbol, btc)
            
            # 利益計算
            profit_pct = 0
            if self.entry_price:
                profit_pct = (current_price - self.entry_price) / self.entry_price * 100
            
            self.in_position = False
            self.entry_price = None
            
            logging.info(f"✅ 売り: {btc:.6f} BTC @ ¥{current_price:,.0f} (利益: {profit_pct:+.2f}%)")
            logging.info(f"注文ID: {order['id']}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ 売りエラー: {e}")
            return False
    
    def print_status(self, current_price, momentum):
        """
        現在の状態を表示
        
        Args:
            current_price: 現在価格
            momentum: モメンタム値
        """
        jpy, btc = self.get_balance()
        
        logging.info("=" * 60)
        logging.info(f"現在価格: ¥{current_price:,.0f}")
        logging.info(f"モメンタム({self.lookback}日): {momentum:+.2%}")
        logging.info(f"JPY残高: ¥{jpy:,.0f}")
        logging.info(f"BTC残高: {btc:.6f} BTC (≈ ¥{btc * current_price:,.0f})")
        logging.info(f"ポジション: {'保有中' if self.in_position else 'なし'}")
        
        if self.in_position and self.entry_price:
            unrealized_pnl = (current_price - self.entry_price) / self.entry_price * 100
            logging.info(f"エントリー価格: ¥{self.entry_price:,.0f}")
            logging.info(f"含み損益: {unrealized_pnl:+.2f}%")
        
        logging.info("=" * 60)
    
    def run(self):
        """
        Botのメインループ
        """
        logging.info("🚀 モメンタムBot 起動")
        logging.info(f"取引ペア: {self.symbol}")
        
        # 取引所接続確認
        try:
            self.exchange.load_markets()
            logging.info(f"取引所接続成功: {self.exchange.id}")
        except Exception as e:
            logging.error(f"取引所接続失敗: {e}")
            return
        
        # 初期残高表示
        jpy, btc = self.get_balance()
        logging.info(f"JPY残高: ¥{jpy:,.2f}")
        logging.info(f"BTC残高: {btc:.6f} BTC")
        
        while True:
            try:
                # 価格データ取得
                prices = self.get_price_history()
                if prices is None or len(prices) == 0:
                    logging.warning("価格データ取得失敗、60秒後に再試行")
                    time.sleep(60)
                    continue
                
                current_price = prices.iloc[-1]
                
                # ストップロスチェック
                if self.check_stop_loss(current_price):
                    logging.warning("⚠️ ストップロス発動")
                    self.execute_sell(current_price)
                    time.sleep(3600)  # 1時間待機
                    continue
                
                # モメンタム計算
                momentum = self.calculate_momentum(prices)
                
                # ステータス表示
                self.print_status(current_price, momentum)
                
                # 売買シグナル判定
                if momentum > self.threshold and not self.in_position:
                    logging.info("🔔 買いシグナル")
                    self.execute_buy(current_price)
                    
                elif momentum < -self.threshold and self.in_position:
                    logging.info("🔔 売りシグナル")
                    self.execute_sell(current_price)
                
                # 1時間待機
                logging.info("次回チェック: 1時間後\n")
                time.sleep(3600)
                
            except KeyboardInterrupt:
                logging.info("\n⏹️ Bot停止")
                break
                
            except Exception as e:
                logging.error(f"❌ エラー: {e}")
                time.sleep(3600)


if __name__ == "__main__":
    # 設定ファイル読み込み
    try:
        with open('momentum_config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.error("設定ファイル 'momentum_config.json' が見つかりません")
        exit(1)
    except json.JSONDecodeError:
        logging.error("設定ファイルのJSON形式が不正です")
        exit(1)
    
    # Bot起動
    bot = MomentumBotJPY(config)
    bot.run()
