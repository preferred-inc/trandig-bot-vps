# Momentum Trading Bot

暗号資産（BTC/USDT）のモメンタムトレーディングBot

## バックテスト結果

- **年率リターン**: 104.58%
- **取引回数**: 145回/年
- **期間**: 2024年1月〜12月

## インストール

### 1. 必要なソフトウェア

```bash
apt update && apt install -y python3 python3-pip python3-venv
```

### 2. リポジトリクローン

```bash
git clone https://github.com/YOUR_USERNAME/momentum-trading-bot.git
cd momentum-trading-bot
```

### 3. 仮想環境作成

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. ライブラリインストール

```bash
pip install ccxt pandas numpy
```

### 5. 設定ファイル編集

```bash
nano momentum_config.json
```

以下を編集：
- `api_key`: BinanceのAPIキー
- `api_secret`: BinanceのAPIシークレット

### 6. Bot起動

```bash
python3 momentum_bot_production.py
```

## ファイル説明

- `momentum_bot_production.py`: 本番用Botコード
- `momentum_config.json`: 設定ファイル
- `backtest_csv.py`: バックテストシステム
- `advanced_strategies.py`: 複数戦略の実装
- `SETUP_GUIDE.pdf`: 詳細セットアップガイド
- `final_trading_report.pdf`: 最終レポート

## 注意事項

- APIキーに出金権限を付与しないでください
- 必ずIP制限を設定してください
- 最初は少額でテストしてください

## サポート

詳細は `SETUP_GUIDE.pdf` を参照してください。
