from datetime import datetime, timedelta
import os
import pybotters
from pathlib import Path
import asyncio
import sys
import json
import traceback
from discord import notify_error_discord, notify_dual_discord, notify_discord

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

config_path = Path(__file__).parent.parent / 'config' / 'config.json'
with open(config_path, encoding='utf-8') as f:
    config = json.load(f)
apis = {"bybit": [config['api_key'], config['api_secret']]}

symbols = ['BTCUSDT', 'ETHUSDT', 'SUIUSDT', 'SOLUSDT']
max_holding_bars = {'BTCUSDT':1312, 'ETHUSDT':608, 'SUIUSDT':968, 'SOLUSDT':968}
file_name = 'position_status.json'
url = 'https://api.bybit.com/v5/order/create'

def load_positions():
    """ポジション状態を読み込み"""
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r') as f:
                content = f.read().strip()  # 空白文字を除去
                if not content:  # 空のファイルの場合
                    print("📝 position_status.json が空です")
                    return {}
                
                positions = json.loads(content)
                
                # 文字列をdatetimeに変換
                for symbol, info in positions.items():
                    if 'timestamp' in info:
                        try:
                            info['timestamp'] = datetime.fromisoformat(info['timestamp'])
                        except ValueError:
                            print(f"⚠️ {symbol} の timestamp 形式が不正です")
                            continue
                            
                return positions
                
        except json.JSONDecodeError as e:
            print(f"❌ position_status.json の JSON形式が不正です: {str(e)}")
            notify_error_discord(subtitle="JSON形式エラー", error_message=f"position_status.json: {str(e)}")
            return {}
        except Exception as e:
            print(f"❌ ファイル読み込みエラー: {str(e)}")
            notify_error_discord(subtitle="ファイル読み込みエラー", error_message=str(e))
            return {}
    
    return {}

def save_positions(positions):
    """ポジション状態を保存"""
    # datetimeを文字列に変換
    positions_to_save = {}
    for symbol, info in positions.items():
        positions_to_save[symbol] = info.copy()
        if 'timestamp' in info and hasattr(info['timestamp'], 'isoformat'):
            positions_to_save[symbol]['timestamp'] = info['timestamp'].isoformat()
    
    with open(file_name, 'w') as f:
        json.dump(positions_to_save, f, indent=2)

async def close_position(symbol, positions, client):
    """ポジションをクローズ"""
    if symbol not in positions:
        return
        
    position_info = positions[symbol]
    now = datetime.now()
    close_hours = max_holding_bars[symbol] / 4

    # 時間判定
    if 'timestamp' in position_info:
        if isinstance(position_info['timestamp'], str):
            try:
                timestamp = datetime.fromisoformat(position_info['timestamp'])
            except ValueError:
                print(f"⚠️ {symbol} timestamp変換エラー")
                timestamp = now
        else:
            timestamp = position_info['timestamp']
    else:
        timestamp = now
        notify_error_discord(subtitle="timestamp不足", error_message=f"{symbol}でtimestampが見つかりません")
        
    # 保有時間チェック
    if now <= timestamp + timedelta(hours=close_hours):
        return
    
    try:
        params = {
            'category': "linear",
            'symbol': symbol,
            'orderType': "Market",
            'side': position_info["side"],
            'qty': str(position_info['qty']),
        }
        
        response = await client.fetch("POST", url=url, data=params)
        
        # レスポンスの詳細チェック
        if not response.text:
            print(f"❌ {symbol} 空のレスポンス")
            notify_error_discord(subtitle="API応答なし", error_message=f"{symbol}で空のレスポンスが返されました")
            return
        
        print(f"🔍 {symbol} レスポンス: {response.text[:200]}...")  # デバッグ用
        
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as e:
            print(f"❌ {symbol} JSON解析エラー: {str(e)}")
            print(f"❌ レスポンス内容: '{response.text}'")
            notify_error_discord(
                subtitle="JSON解析エラー", 
                error_message=f"{symbol}: {str(e)}\nレスポンス: {response.text[:500]}"
            )
            return
        
        # API結果チェック
        if result.get('retCode') == 0:
            print(f"✅ {symbol} クローズ成功")
            notify_discord(
                symbol=symbol,
                qty=position_info['qty'], 
                entry_price=position_info.get('entry_price', 'N/A'), 
                exit_price=position_info.get('exit_price', 'Market価格')
            )
            del positions[symbol]
            save_positions(positions)
        else:
            error_msg = result.get('retMsg', 'Unknown error')
            print(f"❌ {symbol} クローズ失敗: {error_msg}")
            notify_error_discord(subtitle="クローズ失敗", error_message=f"{symbol}: {error_msg}")
            
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"❌ {symbol} 予期しないエラー: {str(e)}")
        notify_error_discord(subtitle=f"{symbol} クローズ処理中にエラー発生", error_message=error_msg)

async def main():
    print(f"🔍 ポジション監視開始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        positions = load_positions()
        if not positions:
            print("📝 監視対象のポジションはありません")
            return
        
        print(f"📊 監視対象: {list(positions.keys())}")
        
        async with pybotters.Client(apis=apis) as client:
            tasks = []
            for symbol in symbols:
                if symbol in positions:
                    tasks.append(close_position(symbol, positions, client))
            
            if tasks:
                await asyncio.gather(*tasks)
                print(f"✅ ポジション監視完了 - {len(tasks)}件処理")
                notify_dual_discord(msg=f"✅ ポジションうぉっちゃ～{len(tasks)}処理執行")
            else:
                print("📝 処理対象のポジションはありませんでした")
            
            notify_dual_discord(msg="✅ ポジションうぉっちゃ～動作正常")
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"❌ メイン処理エラー: {str(e)}")
        notify_error_discord(
            subtitle="ポジション監視システムエラー",
            error_message=error_msg
        )

if __name__ == '__main__':
    asyncio.run(main())