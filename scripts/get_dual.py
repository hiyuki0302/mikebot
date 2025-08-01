import pybotters
import numpy as np
import pandas as pd
import json
import asyncio

class mikeneko_dual:
    def __init__(self, symbol:str, timeframe:str, client: pybotters.Client):
        self.symbol = symbol
        self.timeframe = timeframe  
        self.results = []
        self.df = pd.DataFrame()
        self.client: pybotters.Client = client
        self.base_url = 'https://api.bybit.com'
        
    async def get_Kline(self):
        """ローソク足を取得し、デュアルフラクタル判定"""
        endpoint = "/v5/market/kline"
        url = f"{self.base_url}{endpoint}"
        params = {
            'category': "linear",
            'symbol': self.symbol,
            'interval' : self.timeframe,
            'limit' : "300"
        }

        res = await self.client.fetch("GET", url=url, params=params)
        text = res.text
        data = json.loads(text)
        data = data.get('result', {}).get('list', [])
        self.df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]).astype(float)
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"].astype("int64"), unit='ms', utc=True) + pd.Timedelta(hours=9)
        self.df = self.df.sort_values("timestamp").reset_index(drop=True).dropna()

        if self.df.empty: # データがうまく取得できていない場合スキップ
            return
        
        dual_fractals = {}
        array_high = self.df['high'].values
        array_low = self.df['low'].values

        high_fractals = (
            (array_high[2:-2] > array_high[0:-4]) &
            (array_high[2:-2] > array_high[1:-3]) &
            (array_high[2:-2] > array_high[3:-1]) &
            (array_high[2:-2] > array_high[4:])
        )

        low_fractals = (
            (array_low[2:-2] < array_low[0:-4]) &
            (array_low[2:-2] < array_low[1:-3]) &
            (array_low[2:-2] < array_low[3:-1]) &
            (array_low[2:-2] < array_low[4:])
        )
        
        dual_fractal = high_fractals & low_fractals
        dual_indices = np.where(dual_fractal)[0] + 2
        duals = self.df.iloc[dual_indices]
        dual_fractals[self.timeframe] = pd.DataFrame(duals)
        dual_fractal = high_fractals & low_fractals
        dual_indices = np.where(dual_fractal)[0] + 2
        
        if len(dual_indices) > 0:
            duals = self.df.iloc[dual_indices].copy()
            duals['symbol'] = self.symbol
            duals['timeframe'] = self.timeframe
            return duals
    
async def run(symbol,client):
    results = []
    timeframes = ['15', '60', '240']
    for timeframe in timeframes:
        bot = mikeneko_dual(symbol, timeframe, client)
        result = await bot.get_Kline()
        if result is not None and not result.empty:
            results.append(result)
    return results

async def main():
    all_results = []
    symbols = ['BTCUSDT', 'ETHUSDT', 'SUIUSDT', 'SOLUSDT']
    async with pybotters.Client() as client:
        symbol_results =    await asyncio.gather(*(run(symbol, client)for symbol in symbols ))

    for results in symbol_results:
            all_results.extend(results)

    combined_df = pd.concat(all_results, ignore_index=True)
    print(combined_df)

if __name__ == "__main__":
    asyncio.run(main())