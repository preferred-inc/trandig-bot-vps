#!/usr/bin/env python3
"""
Momentum Trading Bot for BTC/JPY with Safety Features
Binance Japan対応版 + Slack通知 + 安全機能
"""
import ccxt
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from collections import deque
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
        """Slackにメッセージを送信"""
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
        self.send("🚀 *Trading Bot 起動*\n取引ペア: BTC/JPY\n安全機能: 有効", "good")
    
    def send_heartbeat(self, price, momentum, jpy_balance, btc_balance):
        """定期通知"""
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
    
    def send_volatility_alert(self, change_pct, timeframe):
        """急激な変動通知"""
        message = f"""⚡ *急激な価格変動検知*
変動率: {change_pct:+.2f}%
期間: {timeframe}
注意: 市場が不安定です"""
        self.send(message, "warning")
    
    def send_emergency_stop(self, reason):
        """緊急停止通知"""
        message = f"""🛑 *緊急停止*
理由: {reason}
Bot は取引を停止しました"""
        self.send(message, "danger")
    
    def send_daily_loss_limit(self, loss_pct):
        """1日損失リミット通知"""
        message = f"""🛑 *1日損失リミット到達*
本日の損失: {loss_pct:.2f}%
本日の取引を停止します
明日0時に自動再開します"""
        self.send(message, "danger")
    
    def send_error(self, error_message):
        """エラー通知"""
        message = f"""❌ *エラー発生*
{error_message}"""
        self.send(message, "danger")


class SafetyMonitor:
    """安全監視クラス"""
    
    def __init__(self, config, slack):
        self.slack = slack
        
        # 急激な変動検知設定
        self.volatility_alert_threshold = config.get('volatility_alert_threshold', 0.05)  # 5%
        self.volatility_stop_threshold = config.get('volatility_stop_threshold', 0.10)  # 10%
        self.price_history = deque(maxlen=12)  # 1時間分（5分×12）
        
        # 損失リミット設定
        self.daily_loss_limit = config.get('daily_loss_limit', 0.05)  # 5%
        self.daily_start_balance = None
        self.last_reset_date = datetime.now().date()
        
        # 異常検知設定
        self.api_error_count = 0
        self.api_error_threshold = 3
        self.last_balance_check = None
        
        # 緊急停止フラグ
        self.emergency_stop = False
        self.daily_trading_stopped = False
        
        logging.info("安全監視システム初期化完了")
    
    def check_volatility(self, current_price):
        """
        急激な変動をチェック
        
        Returns:
            tuple: (alert, stop) - 通知すべきか、停止すべきか
        """
        self.price_history.append({
            'price': current_price,
            'time': datetime.now()
        })
        
        if len(self.price_history) < 2:
            return False, False
        
        # 5分間の変動チェック
        recent_change = (current_price - self.price_history[-2]['price']) / self.price_history[-2]['price']
        
        # 1時間の変動チェック（12個のデータがある場合）
        if len(self.price_history) >= 12:
            hour_change = (current_price - self.price_history[0]['price']) / self.price_history[0]['price']
            
            if abs(hour_change) >= self.volatility_stop_threshold:
                logging.warning(f"⚡ 1時間で{hour_change:+.2%}の変動検知")
                self.slack.send_volatility_alert(hour_change * 100, "1時間")
                self.slack.send_emergency_stop(f"1時間で{hour_change:+.2%}の急激な変動")
                self.emergency_stop = True
                return True, True
        
        if abs(recent_change) >= self.volatility_alert_threshold:
            logging.warning(f"⚡ 5分間で{recent_change:+.2%}の変動検知")
            self.slack.send_volatility_alert(recent_change * 100, "5分間")
            return True, False
        
        return False, False
    
    def check_daily_loss(self, current_balance):
        """
        1日の損失リミットをチェック
        
        Returns:
            bool: 取引を停止すべきか
        """
        today = datetime.now().date()
        
        # 日付が変わったらリセット
        if today != self.last_reset_date:
            self.daily_start_balance = current_balance
            self.last_reset_date = today
            self.daily_trading_stopped = False
            logging.info(f"日次リセット: 開始残高 ¥{current_balance:,.0f}")
            return False
        
        # 初回設定
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance
            return False
        
        # 損失計算
        loss_pct = (current_balance - self.daily_start_balance) / self.daily_start_balance
        
        if loss_pct < -self.daily_loss_limit:
            if not self.daily_trading_stopped:
                logging.warning(f"🛑 1日損失リミット到達: {loss_pct:.2%}")
                self.slack.send_daily_loss_limit(loss_pct * 100)
                self.daily_trading_stopped = True
            return True
        
        return False
    
    def record_api_error(self):
        """APIエラーを記録"""
        self.api_error_count += 1
        logging.warning(f"APIエラー記録: {self.api_error_count}回目")
        
        if self.api_error_count >= self.api_error_threshold:
            logging.error("🛑 APIエラーが連続発生")
            self.slack.send_emergency_stop(f"APIエラーが{self.api_error_count}回連続発生")
            self.emergency_stop = True
            return True
        
        return False
    
    def reset_api_error(self):
        """APIエラーカウントをリセット"""
        if self.api_error_count > 0:
            logging.info("APIエラーカウントをリセット")
            self.api_error_count = 0
    
    def check_balance_anomaly(self, current_balance):
        """残高の異常をチェック"""
        if self.last_balance_check is None:
            self.last_balance_check = current_balance
            return False
        
        # 前回から50%以上減少したら警告
        change = (current_balance - self.last_balance_check) / self.last_balance_check
        
        if change < -0.5:
            logging.error(f"🚨 残高が急激に減少: {change:.2%}")
            self.slack.send_error(f"残高異常検知: {change:.2%}の減少")
            return True
        
        self.last_balance_check = current_balance
        return False
    
    def should_stop_trading(self):
        """取引を停止すべきか"""
        return self.emergency_stop or self.daily_trading_stopped


class MomentumBotSafe:
    def __init__(self, config):
        """モメンタムBot初期化（安全機能付き）"""
        self.exchange = ccxt.binance({
            'apiKey': config['api_key'],
            'secret': config['api_secret'],
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        self.symbol = config['symbol']
        self.lookback = config['lookback']
        self.threshold = config['threshold']
        self.stop_loss_pct = config['stop_loss_pct']
        
        self.in_position = False
        self.entry_price = None
        
        # Slack通知
        self.slack = SlackNotifier(config.get('slack_webhook_url', ''))
        
        # 安全監視
        self.safety = SafetyMonitor(config, self.slack)
        
        # 定期通知用
        self.heartbeat_counter = 0
        self.heartbeat_interval = 6
        
        logging.info(f"Bot初期化完了: {self.symbol}")
        logging.info(f"安全機能: 有効")
    
    def get_price_history(self):
        """過去価格データを取得"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, '1d', limit=self.lookback + 10)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            self.safety.reset_api_error()
            return df['close']
        except Exception as e:
            logging.error(f"価格データ取得エラー: {e}")
            self.safety.record_api_error()
            return None
    
    def calculate_momentum(self, prices):
        """モメンタムを計算"""
        if len(prices) < self.lookback:
            return 0
        return prices.pct_change(self.lookback).iloc[-1]
    
    def check_stop_loss(self, current_price):
        """ストップロス判定"""
        if not self.in_position or self.entry_price is None:
            return False
        loss_pct = (current_price - self.entry_price) / self.entry_price * 100
        return loss_pct < -self.stop_loss_pct
    
    def get_balance(self):
        """残高を取得"""
        try:
            balance = self.exchange.fetch_balance()
            jpy = balance['JPY']['free'] if 'JPY' in balance else 0
            btc = balance['BTC']['free'] if 'BTC' in balance else 0
            self.safety.reset_api_error()
            return jpy, btc
        except Exception as e:
            logging.error(f"残高取得エラー: {e}")
            self.safety.record_api_error()
            return 0, 0
    
    def execute_buy(self, current_price):
        """買い注文を実行"""
        try:
            jpy, btc = self.get_balance()
            if jpy < 1000:
                logging.warning(f"残高不足: ¥{jpy:,.0f}")
                return False
            
            amount_btc = (jpy * 0.95) / current_price
            if amount_btc < 0.0001:
                logging.warning(f"注文量が最小値未満: {amount_btc:.6f} BTC")
                return False
            
            order = self.exchange.create_market_buy_order(self.symbol, amount_btc)
            self.in_position = True
            self.entry_price = current_price
            
            logging.info(f"✅ 買い: {amount_btc:.6f} BTC @ ¥{current_price:,.0f}")
            self.slack.send_buy(amount_btc, current_price)
            self.safety.reset_api_error()
            return True
            
        except Exception as e:
            logging.error(f"❌ 買いエラー: {e}")
            self.slack.send_error(f"買い注文エラー: {str(e)}")
            self.safety.record_api_error()
            return False
    
    def execute_sell(self, current_price, is_stop_loss=False):
        """売り注文を実行"""
        try:
            jpy, btc = self.get_balance()
            if btc < 0.0001:
                logging.warning(f"BTC残高不足: {btc:.6f} BTC")
                return False
            
            order = self.exchange.create_market_sell_order(self.symbol, btc)
            
            profit_pct = 0
            if self.entry_price:
                profit_pct = (current_price - self.entry_price) / self.entry_price * 100
            
            self.in_position = False
            self.entry_price = None
            
            logging.info(f"✅ 売り: {btc:.6f} BTC @ ¥{current_price:,.0f} (利益: {profit_pct:+.2f}%)")
            
            if is_stop_loss:
                self.slack.send_stop_loss(btc, current_price, profit_pct)
            else:
                self.slack.send_sell(btc, current_price, profit_pct)
            
            self.safety.reset_api_error()
            return True
            
        except Exception as e:
            logging.error(f"❌ 売りエラー: {e}")
            self.slack.send_error(f"売り注文エラー: {str(e)}")
            self.safety.record_api_error()
            return False
    
    def print_status(self, current_price, momentum):
        """現在の状態を表示"""
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
        
        # 定期通知
        self.heartbeat_counter += 1
        if self.heartbeat_counter >= self.heartbeat_interval:
            self.slack.send_heartbeat(current_price, momentum, jpy, btc)
            self.heartbeat_counter = 0
    
    def run(self):
        """Botのメインループ"""
        logging.info("🚀 モメンタムBot 起動（安全機能付き）")
        logging.info(f"取引ペア: {self.symbol}")
        
        try:
            self.exchange.load_markets()
            logging.info(f"取引所接続成功: {self.exchange.id}")
        except Exception as e:
            logging.error(f"取引所接続失敗: {e}")
            self.slack.send_error(f"取引所接続失敗: {str(e)}")
            return
        
        jpy, btc = self.get_balance()
        logging.info(f"JPY残高: ¥{jpy:,.2f}")
        logging.info(f"BTC残高: {btc:.6f} BTC")
        
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
                
                # 急激な変動チェック
                alert, stop = self.safety.check_volatility(current_price)
                if stop:
                    logging.error("🛑 急激な変動により取引停止")
                    if self.in_position:
                        self.execute_sell(current_price)
                    time.sleep(3600)
                    continue
                
                # 1日損失リミットチェック
                jpy, btc = self.get_balance()
                total_balance = jpy + (btc * current_price)
                if self.safety.check_daily_loss(total_balance):
                    logging.warning("🛑 1日損失リミット到達、取引停止中")
                    time.sleep(3600)
                    continue
                
                # 残高異常チェック
                self.safety.check_balance_anomaly(total_balance)
                
                # 緊急停止チェック
                if self.safety.should_stop_trading():
                    logging.error("🛑 緊急停止モード")
                    time.sleep(3600)
                    continue
                
                # ストップロスチェック
                if self.check_stop_loss(current_price):
                    logging.warning("⚠️ ストップロス発動")
                    self.execute_sell(current_price, is_stop_loss=True)
                    time.sleep(3600)
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
    try:
        with open('momentum_config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.error("設定ファイル 'momentum_config.json' が見つかりません")
        exit(1)
    except json.JSONDecodeError:
        logging.error("設定ファイルのJSON形式が不正です")
        exit(1)
    
    bot = MomentumBotSafe(config)
    bot.run()
