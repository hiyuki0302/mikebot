import traceback
from pathlib import Path
import sys
import pybotters
import asyncio
import os
import json
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, getcontext
from discord import entry_discord, notify_error_discord, notify_dual_discord

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

config_path = Path(__file__).parent.parent / 'config' / 'config.json'
with open(config_path, encoding='utf-8') as f:
    config = json.load(f)
    
apis = {"bybit": [config['api_key'], config['api_secret']]}
dual = []

class mikeBot:
    def __init__(self, symbol:str, client: pybotters.Client):
        self.symbol = symbol
        self.leverage = 20
        self.padx = {'BTCUSDT':24, 'ETHUSDT':22, 'SUIUSDT':28, 'SOLUSDT':21}
        self.volatility_threshold = {'BTCUSDT':0.4, 'ETHUSDT':1.4, 'SUIUSDT':1.4, 'SOLUSDT': 1.3}
        self.results = []
        self.df = pd.DataFrame()

        # 注文
        self.risk_pct = 0.07
        self.min_lot_sizes = {
            'BTCUSDT': 0.001,
            'ETHUSDT': 0.01,
            'SUIUSDT': 10,
            'SOLUSDT': 0.1,
        }
        self.ticksize = {
            'BTCUSDT': 0.1,
            'ETHUSDT': 0.01,
            'SUIUSDT': 0.0001,
            'SOLUSDT': 0.01,
        }
        self.state_file = 'position_status.json'
        self.load_states()

        # API関連
        self.base_url = 'https://api.bybit.com'
        self.apis = {"bybit": [config['api_key'], config['api_secret']]}
        self.client: pybotters.Client = client

    async def get_Kline(self):
        """ローソク足を取得し、デュアルフラクタル判定"""
        endpoint = "/v5/market/kline"
        url = f"{self.base_url}{endpoint}"
        params = {
            'category': "linear",
            'symbol': self.symbol,
            'interval' : "15", #15分足
            'limit' : "500" # 500本
        }

        res = await self.client.fetch("GET", url=url, params=params)
        text = res.text
        data = json.loads(text)
        data = data.get('result', {}).get('list', [])
        self.df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]).astype(float)
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"].astype("int64"), unit='ms', utc=True) + pd.Timedelta(hours=9)
        self.df = self.df.sort_values("timestamp").reset_index(drop=True).dropna()
        
        if self.df.empty: # データがうまく取得できていない場合スキップ
            notify_error_discord(subtitle="ローソク足データが空！",error_message=f"{self.symbol}のデータ取得失敗")
            return
        
        # ADXの計算とNoneチェック
        adx_result = ta.adx(self.df["high"], self.df["low"], self.df["close"], length=14)
        if adx_result is None or "ADX_14" not in adx_result:
            notify_error_discord(subtitle="ADX計算エラー", error_message=f"{self.symbol}: ADX計算に失敗しました")
            return
        
        self.df["ADX"] = adx_result["ADX_14"]
        
        # ADXカラムにNaNが含まれている場合のチェック
        if self.df["ADX"].isna().all():
            notify_error_discord(subtitle="ADX計算エラー", error_message=f"{self.symbol}: ADX値がすべてNaNです")
            return
        
        # フィボナッチレベルの計算
        diff = self.df["high"] - self.df["low"]
        self.df["fibo_long"] = self.df["high"] - diff * 4.236
        self.df["fibo_short"] = self.df["low"] + diff * 4.236
        self.df["profit_long_1.5"] = self.df["high"] - diff * 1.5
        self.df["profit_short_1.5"] = self.df["low"] + diff * 1.5
        
        # デュアルフラクタル検出
        for i in range(len(self.df) - 144, len(self.df) - 2): # 144本前までのデュアルフラクタル検出
            # インデックスの境界チェック
            if i < 2 or i >= len(self.df) - 2:
                continue
                
            is_high_fractal = all(self.df.iloc[i]['high'] > self.df.iloc[j]['high'] for j in [i - 2, i - 1, i + 1, i + 2])
            is_low_fractal = all(self.df.iloc[i]['low'] < self.df.iloc[j]['low'] for j in [i - 2, i - 1, i + 1, i + 2])

            if is_high_fractal and is_low_fractal:
                self.results.append(self.df.iloc[i])
    
    def load_states(self):
        """保存されたポジション状態を読み込み"""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                self.position_states = json.load(f)
        else:
            self.position_states = {}

    def save_positioninfo(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.position_states, f, indent=2)

    async def torima_entry(self):
        """一定の価格変動があるローソク足を対象に、ADXが20以下の時かつ、フィボナッチリトレースメント4.236以上でロング、以下でショートポジションで注文を入れる。"""
        if self.df.empty: # データがうまく取得できていない場合スキップ
            return
        elif not self.results: # デュアルフラクタルがなかったらスキップ。
            return
        
        self.load_states()
        if self.symbol in self.position_states: # 対象銘柄のポジションがあればスキップ。
            return

        endpoint = '/v5/order/create'
        url = f"{self.base_url}{endpoint}"

        for row in self.results:
            volatility = (row['high'] - row['low']) / row['open'] * 100
            if volatility < self.volatility_threshold[self.symbol]: # 価格変動が一定以下の場合スキップ
                continue
            
            target_price_long = row['fibo_long'] # Seriesで抽出している。
            target_price_short = row['fibo_short']
            sort_row = self.df.sort_values('timestamp', ascending=False)
            target_row = sort_row.iloc[0]
            qty = self.min_lot_sizes.get(self.symbol, 0.001) * self.leverage
            tick_size = self.ticksize[self.symbol]

            # --- ロングエントリー ---
            if target_row['close'] <= target_price_long and target_row['ADX'] <= self.padx[self.symbol]:
                profit_long = (Decimal(str(row['profit_long_1.5'])) // Decimal(str(tick_size))) * Decimal(str(tick_size))
                params = {
                    'category': "linear",
                    'symbol': self.symbol,
                    'orderType': "Market",
                    'side': "Buy",
                    'qty': str(qty),
                    'takeProfit': str(profit_long)
                }
                
                # 注文処理
                try:
                    response = await self.client.fetch("POST", url=url, data=params)
                    text = response.text  
                    response_json = json.loads(text)
                    result_msg = response_json.get('retMsg', 'Unknown')
                    self.position_states[self.symbol] = {
                        'qty': qty,
                        'entry_price': target_row['close'],
                        'exit_price': profit_long,
                        'timestamp': datetime.now().isoformat(),
                        'side': 'Sell' # position_wather.pyでクローズする時のために逆
                    }
                    self.save_positioninfo()
                except Exception as e:
                    error_msg = traceback.format_exc()
                    notify_error_discord(subtitle="注文処理中にエラー発生",error_message=error_msg)
                    break
                
                # Discord通知とCSVファイル作成 
                entry_discord(result=result_msg, symbol=self.symbol, qty=qty, entry_price=target_row['close'], take_profit=row['profit_long_1.5'], direction="LONG")
            
            # --- ショートエントリー ---
            elif target_row['close'] >= target_price_short and target_row['ADX'] <= self.padx[self.symbol]:
                profit_short = (Decimal(str(row['profit_short_1.5'])) // Decimal(str(tick_size))) * Decimal(str(tick_size))
                params = {
                    'category': "linear",
                    'symbol': self.symbol,
                    'orderType': "Market",
                    'side': "Sell",
                    'qty': str(qty),
                    'takeProfit': str(profit_short)
                }
                
                try:
                    response = await self.client.fetch("POST", url=url, data=params)
                    text = response.text  
                    response_json = json.loads(text)
                    result_msg = response_json.get('retMsg', 'Unknown')
                    self.position_states[self.symbol] = {
                    'qty': qty,
                    'entry_price': target_row['close'],
                    'exit_price': profit_short,
                    'timestamp': datetime.now().isoformat(), # 文字列で保存
                    'side': 'Buy' # position_wather.pyでクローズする時のために逆
                    }
                    self.save_positioninfo()
                except Exception as e:
                    error_msg = traceback.format_exc()
                    notify_error_discord(subtitle="注文処理中にエラー発生",error_message=error_msg)
                    break
                
                entry_discord(result=result_msg, symbol=self.symbol, qty=qty, entry_price=target_row['close'], take_profit=row['profit_short_1.5'], direction="SHORT")

async def run_for_symbol(symbol, client: pybotters.Client):
    bot = mikeBot(symbol, client)
    try:
        await bot.get_Kline()
        await bot.torima_entry()
        print(symbol, "処理完了", datetime.now())
    except Exception as e :
        error_msg = traceback.format_exc()
        notify_error_discord(subtitle=f"{symbol}エラー！", error_message=error_msg)
        return

async def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SUIUSDT', 'SOLUSDT']
    async with pybotters.Client(apis=apis) as client:
        await asyncio.gather(*(run_for_symbol(symbol, client) for symbol in symbols))
    notify_dual_discord(msg="✅ エントリー処理完了")

if __name__ == "__main__":
    asyncio.run(main())
