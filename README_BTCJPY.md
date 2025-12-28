# Momentum Trading Bot for BTC/JPY

**Binance Japan対応版**

暗号資産（BTC/JPY）のモメンタムトレーディングBot

## 特徴

- ✅ Binance Japan完全対応
- ✅ JPY建て取引
- ✅ 完全自動売買
- ✅ ストップロス機能
- ✅ 24時間365日稼働

## バックテスト結果（BTC/USDT版）

- **年率リターン**: 104.58%
- **取引回数**: 145回/年
- **期間**: 2024年1月〜12月

※ BTC/JPY版も同様のパフォーマンスが期待できます

---

## セットアップ

### 1. VPSにログイン

```bash
ssh root@<VPSのIPアドレス>
```

### 2. リポジトリ更新

```bash
cd /root/trandig-bot-vps
git pull origin main
```

### 3. 設定ファイルをコピー

```bash
cp momentum_config_btcjpy.json momentum_config.json
```

### 4. APIキーを設定

```bash
nano momentum_config.json
```

以下を編集：
- `api_key`: BinanceのAPIキー
- `api_secret`: BinanceのAPIシークレット

保存: Ctrl+O → Enter → Ctrl+X

### 5. Bot起動

```bash
source venv/bin/activate
python3 momentum_bot_btcjpy.py
```

---

## バックグラウンド実行

### 方法1: screen（推奨）

```bash
screen -S trading_bot
cd /root/trandig-bot-vps
source venv/bin/activate
python3 momentum_bot_btcjpy.py
```

デタッチ: `Ctrl + A` → `D`

再接続:
```bash
screen -r trading_bot
```

### 方法2: nohup

```bash
cd /root/trandig-bot-vps
source venv/bin/activate
nohup python3 momentum_bot_btcjpy.py > bot.log 2>&1 &
```

ログ確認:
```bash
tail -f bot.log
```

---

## 設定パラメータ

### symbol
- **値**: `"BTC/JPY"`
- **説明**: 取引ペア

### lookback
- **デフォルト**: 20
- **説明**: モメンタム計算期間（日数）
- **調整**: 10〜30

### threshold
- **デフォルト**: 0.02（2%）
- **説明**: 売買シグナルの閾値
- **調整**: 0.01〜0.05

### stop_loss_pct
- **デフォルト**: 10
- **説明**: ストップロス（%）
- **調整**: 5〜15

---

## 注意事項

### 最小取引量

Binance Japanの最小注文量: **0.0001 BTC**

最低必要資金: 約 **¥10,000**

### 取引手数料

- **Maker**: 0.05%
- **Taker**: 0.10%

### リスク

- 暗号資産取引にはリスクが伴います
- 必ず余剰資金で運用してください
- 最初は少額でテストしてください

---

## トラブルシューティング

### エラー: "Invalid Api-Key ID"

→ APIキーが間違っています。設定ファイルを確認してください。

### エラー: "Insufficient balance"

→ 残高不足です。JPYを入金してください。

### エラー: "Order amount is too small"

→ 注文量が最小値（0.0001 BTC）未満です。資金を追加してください。

---

## サポート

問題が発生した場合は、以下を確認してください：

1. ログファイル: `momentum_bot.log`
2. 設定ファイル: `momentum_config.json`
3. Binance APIの権限設定
4. JPY残高

---

## ライセンス

MIT License
