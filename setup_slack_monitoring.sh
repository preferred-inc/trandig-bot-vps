#!/bin/bash
# Slack通知機能とSystemd監視のセットアップスクリプト

set -e

echo "========================================="
echo " Slack通知 + Systemd監視 セットアップ"
echo "========================================="
echo ""

# 必要なパッケージをインストール
echo "[1/6] 必要なパッケージをインストール中..."
pip3 install requests -q

# 設定ファイルをコピー
echo "[2/6] 設定ファイルを準備中..."
if [ ! -f momentum_config.json.backup ]; then
    cp momentum_config.json momentum_config.json.backup
fi

# Slack Webhook URLを設定
echo "[3/6] Slack Webhook URLを入力してください:"
read -p "Webhook URL: " WEBHOOK_URL

# 設定ファイルを更新
cat momentum_config.json.backup | \
    jq --arg webhook "$WEBHOOK_URL" '. + {slack_webhook_url: $webhook}' > momentum_config.json

echo "設定ファイル更新完了"

# Systemdサービスをインストール
echo "[4/6] Systemdサービスをインストール中..."
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

# 既存のscreenセッションを停止
echo "[5/6] 既存のBotを停止中..."
screen -S trading_bot -X quit 2>/dev/null || true
sleep 2

# Systemdサービスを起動
echo "[6/6] Systemdサービスを起動中..."
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

echo ""
echo "========================================="
echo " セットアップ完了！"
echo "========================================="
echo ""
echo "✅ Slack通知が有効になりました"
echo "✅ Systemdで自動再起動が有効になりました"
echo ""
echo "確認コマンド:"
echo "  sudo systemctl status trading-bot"
echo "  tail -f momentum_bot.log"
echo ""
echo "Slackに起動通知が届いているか確認してください。"
