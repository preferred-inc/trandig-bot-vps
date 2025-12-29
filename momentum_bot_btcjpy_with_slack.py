#!/usr/bin/env python3
"""
Momentum Trading Bot for BTC/JPY with Slack Notifications
Binance Japan対応版 + Slack通知機能
"""
import ccxt
import pandas as pd
import time
import json
from datetime import datetime
import logging
import requests
import traceback

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('momentum_bot.log'),
        logging.StreamHandler()
    ]
)

class SlackNotifier:
    """Slack通知クラス"""
    
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url and webhook_url != "YOUR_SLACK_WEBHOOK_URL")
    
    def send(self, message, color="good"):
        """
        Slackにメッセージを送信
        
        Args:
            message: 送信するメッセージ
            color: メッセージの色 (good, warning, danger)
        """
        if not self.enabled:
            return
        
        try:
            payload = {
                "attachments": [{
                    "color": color,
                    "text": message,
                    "footer": "Trading Bot",
                    "ts": int(time.time())
                }]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                logging.error(f"Slack通知エラー: {response.status_code}")
                
        except Exception as e:
            logging.error(f"Slack通知失敗: {e}")
    
    def send_startup(self):
        """起動通知"""
        self.send("🚀 *Trading Bot 起動*\n取引ペア: BTC/JPY", "good")
    
    def send_heartbeat(self, price, momentum, jpy_balance, btc_balance):
        """定期通知（6時間ごと）"""
        message = f"""💓 *Bot 稼働中*
現在価格: ¥{price:,.0f}
モメンタム: {momentum:+.2%}
JPY残高: ¥{jpy_balance:,.0f}
BTC残高: {btc_balance:.6f} BTC"""
        self.send(message, "good")
    
    def send_buy(self, amount, price):
        """買い注文通知"""
        message = f"""🟢 *買い注文実行*
数量: {amount:.6f} BTC
価格: ¥{price:,.0f}
合計: ¥{amount * price:,.0f}"""
        self.send(message, "good")
    
    def send_sell(self, amount, price, profit_pct):
        """売り注文通知"""
        emoji = "🟢" if profit_pct > 0 else "🔴"
        color = "good" if profit_pct > 0 else "danger"
        message = f"""{emoji} *売り注文実行*
数量: {amount:.6f} BTC
価格: ¥{price:,.0f}
合計: ¥{amount * price:,.0f}
損益: {profit_pct:+.2f}%"""
        self.send(message, color)
    
    def send_stop_loss(self, amount, price, loss_pct):
        """ストップロス通知"""
        message = f"""⚠️ *ストップロス発動*
数量: {amount:.6f} BTC
価格: ¥{price:,.0f}
損失: {loss_pct:.2f}%"""
        self.send(message, "danger")
    
    def send_error(self, error_message):
        """エラー通知"""
        message = f"""❌ *エラー発生*
{error_message}"""
        self.send(message, "danger")


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
        
        # Slack通知
        self.slack = SlackNotifier(config.get('slack_webhook_url', ''))
        
        # 定期通知用カウンター
        self.heartbeat_counter = 0
        self.heartbeat_interval = 6  # 6時間ごと
        
        logging.info(f"Bot初期化完了: {self.symbol}")
        logging.info(f"ルックバック: {self.lookback}日")
        logging.info(f"閾値: {self.threshold*100}%")
        logging.info(f"ストップロス: {self.stop_loss_pct}%")
        logging.info(f"Slack通知: {'有効' if self.slack.enabled else '無効'}")
    
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
            
            # Slack通知
            self.slack.send_buy(amount_btc, current_price)
            
            return True
            
        except Exception as e:
            logging.error(f"❌ 買いエラー: {e}")
            self.slack.send_error(f"買い注文エラー: {str(e)}")
            return False
    
    def execute_sell(self, current_price, is_stop_loss=False):
        """
        売り注文を実行
        
        Args:
            current_price: 現在価格
            is_stop_loss: ストップロスによる売却か
            
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
            
            # Slack通知
            if is_stop_loss:
                self.slack.send_stop_loss(btc, current_price, profit_pct)
            else:
                self.slack.send_sell(btc, current_price, profit_pct)
            
            return True
            
        except Exception as e:
            logging.error(f"❌ 売りエラー: {e}")
            self.slack.send_error(f"売り注文エラー: {str(e)}")
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
        
        # 定期通知（6時間ごと）
        self.heartbeat_counter += 1
        if self.heartbeat_counter >= self.heartbeat_interval:
            self.slack.send_heartbeat(current_price, momentum, jpy, btc)
            self.heartbeat_counter = 0
    
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
            self.slack.send_error(f"取引所接続失敗: {str(e)}")
            return
        
        # 初期残高表示
        jpy, btc = self.get_balance()
        logging.info(f"JPY残高: ¥{jpy:,.2f}")
        logging.info(f"BTC残高: {btc:.6f} BTC")
        
        # 起動通知
        self.slack.send_startup()
        
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
                    self.execute_sell(current_price, is_stop_loss=True)
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
                self.slack.send("⏹️ *Bot停止*", "warning")
                break
                
            except Exception as e:
                error_msg = f"予期しないエラー: {str(e)}\n{traceback.format_exc()}"
                logging.error(error_msg)
                self.slack.send_error(error_msg)
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
