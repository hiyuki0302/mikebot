"""
緊急ストップロス監視システム（自動化重視版）
- 動的基準残高管理
- 24時間ごとの自動更新
- 最低限の手動機能のみ
"""

import asyncio
import sys
import json
import os
import traceback
from datetime import datetime
import pybotters
from discord import notify_error_discord, notify_discord, notify_dual_discord

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ===========================================
# 設定
# ===========================================
MAX_LOSS_PERCENTAGE = 0.7      # 50%損失で緊急停止
BALANCE_UPDATE_HOURS = 24       # 24時間ごとに基準残高を自動更新
INITIAL_BALANCE = 30.0       # 初期値（初回のみ使用）

# ファイル設定
with open('config_honban.json', encoding='utf-8') as f:
    config = json.load(f)

apis = {"bybit": [config['api_key'], config['api_secret']]}
base_url = 'https://api.bybit.com'
position_file = 'position_status.json'
balance_file = 'balance_reference.json'

# ===========================================
# 基準残高管理
# ===========================================
def load_reference_balance():
    """基準残高を読み込み"""
    if os.path.exists(balance_file):
        with open(balance_file, 'r') as f:
            data = json.load(f)
            return data['reference_balance'], data['last_update']
    
    # 初回作成
    save_reference_balance(INITIAL_BALANCE)
    return INITIAL_BALANCE, datetime.now().isoformat()

def save_reference_balance(balance):
    """基準残高を保存"""
    data = {
        'reference_balance': balance,
        'last_update': datetime.now().isoformat()
    }
    with open(balance_file, 'w') as f:
        json.dump(data, f, indent=2)

def should_update_balance(last_update_str):
    """基準残高を更新すべきかチェック"""
    last_update = datetime.fromisoformat(last_update_str)
    hours_passed = (datetime.now() - last_update).total_seconds() / 3600
    return hours_passed >= BALANCE_UPDATE_HOURS

# ===========================================
# API関数
# ===========================================
async def get_account_balance(client):
    """統合取引アカウントの資産情報取得"""
    try:
        params = {"accountType": "UNIFIED"}
        endpoint = "/v5/account/wallet-balance"
        url = f"{base_url}{endpoint}"
        res = await client.fetch("GET", url=url, params=params)
        
        if not res.text:
            print("❌ 空のレスポンス")
            return None
            
        data = json.loads(res.text)
        
        if data.get('retCode') != 0:
            print(f"❌ API エラー: {data.get('retMsg')}")
            return None
            
        coins = data['result']['list']
        usdt_info = next(c for acc in coins for c in acc['coin'] if c['coin'] == 'USDT')
        return float(usdt_info['walletBalance'])
        
    except Exception as e:
        print(f"❌ 残高取得エラー: {str(e)}")
        return None

async def get_all_positions_pnl(client):
    """全ポジションの未実現PnLを取得"""
    try:
        endpoint = "/v5/position/list"
        url = f"{base_url}{endpoint}"
        params = {
            'category': 'linear',
            'settleCoin': 'USDT'
        }
        
        response = await client.fetch("GET", url=url, params=params)
        
        if not response.text:
            print("❌ ポジション情報の空レスポンス")
            return 0.0, []
            
        data = json.loads(response.text)
        
        if data.get('retCode') != 0:
            print(f"❌ ポジション取得エラー: {data.get('retMsg')}")
            return 0.0, []
        
        pos_list = data.get('result', {}).get('list', [])
        
        total_pnl = 0.0
        position_details = []
        
        for pos in pos_list:
            size = float(pos.get('size', 0))
            if size > 0:
                symbol = pos.get('symbol')
                pnl = float(pos.get('unrealisedPnl', 0))
                total_pnl += pnl
                position_details.append({
                    'symbol': symbol,
                    'pnl': pnl,
                    'side': pos.get('side'),
                    'size': size
                })
        
        return total_pnl, position_details
        
    except Exception as e:
        print(f"❌ ポジションPnL取得エラー: {str(e)}")
        return 0.0, []

async def emergency_close_position(client, symbol, side, qty):
    """個別ポジションを緊急クローズ"""
    url = f"{base_url}/v5/order/create"
    
    for attempt in range(3):
        try:
            close_side = "Sell" if side == "Buy" else "Buy"
            
            params = {
                'category': "linear",
                'symbol': symbol,
                'orderType': "Market",
                'side': close_side,
                'qty': str(qty),
                'reduceOnly': True
            }
            
            response = await client.fetch("POST", url=url, data=params)
            
            if response.status == 200:
                data = json.loads(response.text)
                if data.get('retCode') == 0:
                    print(f"✅ {symbol} 緊急クローズ成功")
                    return True
                else:
                    print(f"❌ {symbol} クローズ失敗: {data.get('retMsg')}")
            
        except Exception as e:
            print(f"❌ {symbol} エラー: {str(e)}")
        
        if attempt < 2:
            await asyncio.sleep(2)
    
    return False

# ===========================================
# メイン監視ロジック
# ===========================================
async def check_emergency_stop():
    """緊急ストップチェック"""
    
    async with pybotters.Client(apis=apis) as client:
        
        # 1. 現在の残高取得
        current_balance = await get_account_balance(client)
        if current_balance is None:
            print("⚠️ 残高取得失敗")
            return False
        
        # 2. 基準残高の管理
        reference_balance, last_update = load_reference_balance()
        
        # 3. 自動更新チェック
        if should_update_balance(last_update):
            print(f"📊 基準残高自動更新: {reference_balance:.2f} → {current_balance:.2f} USDT")
            reference_balance = current_balance
            save_reference_balance(reference_balance)
        
        # 4. 全ポジションのPnL取得
        total_pnl, position_details = await get_all_positions_pnl(client)
        
        # 5. 損失計算
        total_equity = current_balance + total_pnl
        total_loss = max(0, reference_balance - total_equity)
        loss_percentage = total_loss / reference_balance if reference_balance > 0 else 0
        
        # 6. ログ出力
        print(f"📊 基準残高: {reference_balance:.2f} USDT")
        print(f"📊 現在残高: {current_balance:.2f} USDT")
        print(f"📊 未実現PnL: {total_pnl:.2f} USDT")
        print(f"📊 総資産: {total_equity:.2f} USDT")
        print(f"📊 損失率: {loss_percentage:.1%}")
        
        # 7. 緊急ストップ判定
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            print(f"🚨 緊急ストップ発動！損失率: {loss_percentage:.1%}")
            
            # Discord通知
            pnl_summary = "\n".join([f"{p['symbol']}: {p['pnl']:.2f} USDT" for p in position_details])
            notify_error_discord(
                subtitle="🚨 緊急ストップ発動",
                error_message=f"基準残高: {reference_balance:.0f} USDT\n現在残高: {current_balance:.2f} USDT\n総資産: {total_equity:.2f} USDT\n損失率: {loss_percentage:.1%}\n\n{pnl_summary}"
            )
            
            # 8. 全ポジション強制クローズ
            await execute_emergency_close(client, position_details)
            
            return True
        
        return False

async def execute_emergency_close(client, position_details):
    """全ポジションを緊急クローズ"""
    
    if not position_details:
        return
    
    print(f"🚨 {len(position_details)}個のポジションを緊急クローズします")
    
    success_count = 0
    failed_symbols = []
    
    for pos in position_details:
        symbol = pos['symbol']
        side = pos['side']
        size = pos['size']
        
        success = await emergency_close_position(client, symbol, side, size)
        
        if success:
            success_count += 1
            notify_discord(
                symbol=symbol,
                qty=size,
                entry_price="取得不可",
                exit_price="緊急ストップ"
            )
        else:
            failed_symbols.append(symbol)
    
    # ポジションファイルクリア
    if success_count > 0:
        if os.path.exists(position_file):
            try:
                with open(position_file, 'r') as f:
                    positions = json.load(f)
                
                for pos in position_details:
                    if pos['symbol'] not in failed_symbols and pos['symbol'] in positions:
                        del positions[pos['symbol']]
                
                with open(position_file, 'w') as f:
                    json.dump(positions, f, indent=2)
                    
                print(f"📝 ポジションファイル更新: {success_count}件削除")
            except:
                pass
    
    # 結果通知
    if failed_symbols:
        notify_error_discord(
            subtitle="🚨 緊急クローズ一部失敗",
            error_message=f"成功: {success_count}件\n失敗: {', '.join(failed_symbols)}"
        )

# ===========================================
# 手動機能（最低限）
# ===========================================
def reset_balance(new_balance):
    """手動で基準残高をリセット"""
    save_reference_balance(new_balance)
    print(f"✅ 基準残高を {new_balance:.2f} USDT にリセットしました")

def show_status():
    """現在の状態を表示"""
    reference_balance, last_update = load_reference_balance()
    update_time = datetime.fromisoformat(last_update)
    hours_since_update = (datetime.now() - update_time).total_seconds() / 3600
    
    print(f"📊 基準残高: {reference_balance:.2f} USDT")
    print(f"📊 最終更新: {update_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 更新から: {hours_since_update:.1f}時間経過")
    print(f"📊 次回更新まで: {24 - hours_since_update:.1f}時間")

# ===========================================
# メイン実行
# ===========================================
async def main():
    """メイン実行関数"""
    try:
        print(f"🔍 緊急監視開始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        emergency_triggered = await check_emergency_stop()
        
        if emergency_triggered:
            print("🚨 緊急ストップが実行されました")
        else:
            print("✅ 正常範囲内です")
            notify_dual_discord(msg = "✅ 緊急監視処理完了")
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"❌ 緊急監視エラー: {str(e)}")
        notify_error_discord(
            subtitle="緊急監視システムエラー",
            error_message=error_msg
        )

if __name__ == "__main__":
    # コマンドライン引数で手動機能を実行
    if len(sys.argv) > 1:
        if sys.argv[1] == "reset" and len(sys.argv) > 2:
            reset_balance(float(sys.argv[2]))
        elif sys.argv[1] == "status":
            show_status()
    else:
        asyncio.run(main())