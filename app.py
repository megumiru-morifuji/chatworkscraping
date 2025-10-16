from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

# フィルター対象のキーワード
TARGET_KEYWORDS = [
    "吉田", "金森", "藤田", "原", "プログラミングチーム", "加藤", 
    "野坂", "森田", "大谷", "村上", "斎藤", "備品発注管理", "北館", 
    "社員連絡", "金山", "めぐみる", "鈴木", "浅井", "白石", "山田", 
    "藤原", "堀田"
]

def should_process_room(room_name):
    """ルーム名が対象キーワードを含むかチェック"""
    for keyword in TARGET_KEYWORDS:
        if keyword in room_name:
            return True, keyword
    return False, None

def login_chatwork(driver):
    """Chatworkにログイン（手動）"""
    driver.get("https://www.chatwork.com/login.php")
    
    print("\n" + "="*60)
    print("🔐 手動ログインしてください")
    print("="*60)
    print("1. メールアドレスを入力")
    print("2. reCAPTCHAをクリック（ロボットではありません）")
    print("3. 「続ける」をクリック")
    print("4. パスワードを入力してログイン")
    print("\nログイン完了後、Enterキーを押してください...")
    print("="*60)
    
    input("\n👉 ログイン完了後、Enterを押す >> ")
    
    # ログイン確認
    try:
        WebDriverWait(driver, 5).until(
            lambda d: "chatwork.com/#" in d.current_url or "chatwork.com/gateway" in d.current_url
        )
        print("✅ ログイン確認完了")
    except:
        print("⚠️  ログインURLを確認できませんが続行します")

def get_all_room_urls(driver):
    """サイドバーから全ルームURLを自動取得"""
    print("\n🔍 全ルームを検索中...")
    
    # チャット画面に移動
    driver.get("https://www.chatwork.com/")
    time.sleep(5)
    
    # ルームリストをスクロールして全て表示
    print("  ルームリストをスクロール中...")
    room_list_selectors = [
        "[role='tablist']",
        "[role='list']",
        "#_roomListItems",
        ".roomList",
        "[class*='roomList']"
    ]
    
    room_list = None
    for selector in room_list_selectors:
        try:
            room_list = driver.find_element(By.CSS_SELECTOR, selector)
            print(f"  ✓ ルームリスト検出: {selector}")
            # スクロールして全て読み込み
            for _ in range(20):
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", room_list)
                time.sleep(0.5)
            break
        except:
            continue
    
    # data-rid属性を持つli要素を取得（新UI対応）
    print("\n  ルーム要素を検索中...")
    
    room_elements = []
    element_selectors = [
        "li[data-rid]",
        "li[role='tab'][data-rid]",
        "[data-rid]"
    ]
    
    for selector in element_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                print(f"    ✓ {selector}: {len(elements)}個検出")
                room_elements = elements
                break
        except:
            continue
    
    # data-rid からURLとルーム名を取得
    room_data = []
    
    if room_elements:
        for elem in room_elements:
            rid = elem.get_attribute("data-rid")
            if rid:
                # ChatworkのURL形式でURLを生成
                room_url = f"https://www.chatwork.com/#!rid{rid}"
                
                # ルーム名を取得
                room_name = "Unknown"
                try:
                    label = elem.get_attribute("aria-label")
                    if label:
                        room_name = label
                except:
                    pass
                
                room_data.append({
                    "url": room_url,
                    "name": room_name,
                    "rid": rid
                })
    
    # 旧UIにも対応（念のため）
    if not room_data:
        print("\n  旧UI形式も試行中...")
        old_selectors = [
            "a[href*='#!rid']",
            "a[href*='rid']",
            "._roomLink"
        ]
        
        for selector in old_selectors:
            try:
                links = driver.find_elements(By.CSS_SELECTOR, selector)
                if links:
                    print(f"    ✓ {selector}: {len(links)}個検出")
                    for link in links:
                        href = link.get_attribute("href")
                        name = link.text.strip() or "Unknown"
                        if href and "rid" in href:
                            rid = href.split("rid")[-1]
                            room_data.append({
                                "url": href,
                                "name": name,
                                "rid": rid
                            })
            except:
                continue
    
    # 手動入力モードへのフォールバック
    if not room_data:
        print("\n❌ 自動検出できませんでした")
        return []
    
    # フィルタリング処理
    print(f"\n📊 合計 {len(room_data)}個のルームを検出")
    print(f"\n🔍 対象キーワードでフィルタリング中...")
    print(f"   キーワード: {', '.join(TARGET_KEYWORDS)}")
    
    filtered_rooms = []
    skipped_rooms = []
    
    for room in room_data:
        should_process, matched_keyword = should_process_room(room["name"])
        if should_process:
            filtered_rooms.append(room)
            print(f"  ✓ [{matched_keyword}] {room['name'][:40]} (rid{room['rid']})")
        else:
            skipped_rooms.append(room)
    
    print(f"\n✅ 対象ルーム: {len(filtered_rooms)}個")
    print(f"⏭️  スキップ: {len(skipped_rooms)}個")
    
    if len(filtered_rooms) == 0:
        print("\n⚠️  対象ルームが見つかりませんでした")
        print("\nスキップされたルーム一覧:")
        for room in skipped_rooms[:20]:
            print(f"    - {room['name'][:50]}")
        if len(skipped_rooms) > 20:
            print(f"    ... 他 {len(skipped_rooms) - 20} 件")
    
    return [room["url"] for room in filtered_rooms]

def get_session_cookies(driver):
    """SeleniumのCookieをrequestsセッションに転送"""
    session = requests.Session()
    selenium_cookies = driver.get_cookies()
    
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
    
    return session

def refresh_session(driver):
    """セッションを更新してタイムアウトを防ぐ"""
    try:
        # 現在のURLを保存
        current_url = driver.current_url
        
        # トップページに移動してセッション更新
        driver.get("https://www.chatwork.com/")
        time.sleep(2)
        
        # 元のページに戻る
        driver.get(current_url)
        time.sleep(2)
        
        print("  🔄 セッション更新完了")
    except Exception as e:
        print(f"  ⚠️  セッション更新エラー: {e}")

def download_file(session, url, save_dir, filename):
    """添付ファイルをダウンロード"""
    try:
        save_path = Path(save_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        response = session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"    ✓ ダウンロード: {filename}")
        return str(save_path)
    except Exception as e:
        print(f"    ✗ ダウンロード失敗 ({filename}): {e}")
        return None

def scroll_to_load_all_messages(driver):
    """チャット履歴を全て読み込むまでスクロール（遅延ロード対応）"""
    print("📜 過去のメッセージを読み込み中...")
    
    # チャットエリアを特定
    chat_area = None
    selectors = [
        "div.sc-eBAZHg.kzmpjh",
        "div[tabindex='1']",
        "#_chatText",
        ".cw_chat_body",
        "[role='log']",
        ".chatTimeLineContainer",
        "#_timeLine"
    ]
    
    for selector in selectors:
        try:
            chat_area = driver.find_element(By.CSS_SELECTOR, selector)
            print(f"  ✓ チャットエリア検出: {selector}")
            break
        except:
            continue
    
    if not chat_area:
        print("  ⚠️ チャットエリアが見つかりません")
        print("  スクロールなしで続行します（最近のメッセージのみ取得）")
        time.sleep(3)
        return
    
    previous_message_count = 0
    no_change_count = 0
    max_attempts = 300
    wait_time = 2.5
    session_refresh_interval = 50  # 50回ごとにセッション更新
    
    print(f"  スクロール開始（最大{max_attempts}回試行）...")
    
    for i in range(max_attempts):
        # 定期的にセッション更新
        if i > 0 and i % session_refresh_interval == 0:
            print(f"  ⏱️  長時間処理中 - セッション更新...")
            refresh_session(driver)
        
        messages = driver.find_elements(By.CSS_SELECTOR, "[data-mid]")
        current_count = len(messages)
        
        driver.execute_script("arguments[0].scrollTop = 0", chat_area)
        time.sleep(wait_time)
        
        messages_after_wait = driver.find_elements(By.CSS_SELECTOR, "[data-mid]")
        count_after_wait = len(messages_after_wait)
        
        if count_after_wait == previous_message_count:
            no_change_count += 1
            print(f"    変化なし {no_change_count}/7 ({count_after_wait}件)")
            if no_change_count >= 7:
                print(f"  ✅ 全メッセージ読み込み完了 ({count_after_wait}件)")
                break
        else:
            no_change_count = 0
            print(f"    {count_after_wait}件のメッセージを検出（+{count_after_wait - previous_message_count}件）")
        
        previous_message_count = count_after_wait
        
        if i > 0 and i % 20 == 0:
            print(f"    継続中... {i}/{max_attempts}回 ({count_after_wait}件)")
    
    if no_change_count < 7:
        print(f"  ⚠️ 最大試行回数に達しました ({previous_message_count}件取得）")
    
    driver.execute_script("arguments[0].scrollTop = 0", chat_area)
    time.sleep(2)
    
    final_count = len(driver.find_elements(By.CSS_SELECTOR, "[data-mid]"))
    print(f"  📊 最終取得件数: {final_count}件")

def extract_message_data(msg, session, download_dir, driver):
    """個別メッセージからデータを抽出"""
    data = {
        "message_id": None,
        "sender": "Unknown",
        "company": "",
        "body": "",
        "timestamp": "",
        "attachments": [],
        "is_task": False
    }
    
    try:
        # message_idを取得してから、以降はこのIDで要素を再取得
        data["message_id"] = msg.get_attribute("data-mid")
        
        # 要素が無効になった場合に備えて、message_idで再検索する関数
        def get_fresh_element():
            try:
                return driver.find_element(By.CSS_SELECTOR, f"[data-mid='{data['message_id']}']")
            except:
                return msg  # 見つからない場合は元の要素を返す
        
        # 送信者名（新UI対応）
        sender_selectors = [
            "[data-testid='timeline_user-name']",
            "p[data-testid='timeline_user-name']",
            ".sc-iPahhU",
            ".chatTimeLineNameBox__name",
            "[class*='userName']"
        ]
        for selector in sender_selectors:
            try:
                fresh_msg = get_fresh_element()
                sender = fresh_msg.find_element(By.CSS_SELECTOR, selector)
                data["sender"] = sender.text.strip()
                if data["sender"]:
                    break
            except:
                continue
        
        # 会社名・所属（新UI）
        try:
            fresh_msg = get_fresh_element()
            company_elem = fresh_msg.find_element(By.CSS_SELECTOR, ".sc-fjhLSj")
            data["company"] = company_elem.text.strip()
        except:
            pass
        
        # メッセージ本文（新UI対応）
        body_selectors = [
            "pre.sc-fbFiXs",
            "pre span",
            "pre",
            ".chatTimeLineTxt",
            "[class*='message']"
        ]
        for selector in body_selectors:
            try:
                fresh_msg = get_fresh_element()
                body = fresh_msg.find_element(By.CSS_SELECTOR, selector)
                data["body"] = body.text.strip()
                if data["body"]:
                    break
            except:
                continue
        
        # タイムスタンプ（新UI対応）
        time_selectors = [
            "._timeStamp",
            "[data-tm]",
            "div[data-tm]",
            "time",
            "[datetime]"
        ]
        for selector in time_selectors:
            try:
                fresh_msg = get_fresh_element()
                time_elem = fresh_msg.find_element(By.CSS_SELECTOR, selector)
                data_tm = time_elem.get_attribute("data-tm")
                datetime_attr = time_elem.get_attribute("datetime")
                text = time_elem.text.strip()
                
                if datetime_attr:
                    data["timestamp"] = datetime_attr
                elif data_tm:
                    data["timestamp"] = f"unix:{data_tm}"
                elif text:
                    data["timestamp"] = text
                
                if data["timestamp"]:
                    break
            except:
                continue
        
        # 添付ファイルの検出とダウンロード
        file_selectors = [
            "a[download]",
            "[class*='file']",
            ".cw_message_file",
            "a[href*='storage.chatwork.com']"
        ]
        
        for selector in file_selectors:
            try:
                fresh_msg = get_fresh_element()
                files = fresh_msg.find_elements(By.CSS_SELECTOR, selector)
                for file_elem in files:
                    try:
                        file_url = file_elem.get_attribute("href") or file_elem.get_attribute("data-url")
                        file_name = file_elem.text.strip() or file_elem.get_attribute("download") or file_elem.get_attribute("title") or "unknown_file"
                        
                        if file_url and 'storage.chatwork.com' in file_url:
                            local_path = download_file(session, file_url, download_dir, file_name)
                            
                            data["attachments"].append({
                                "type": "file",
                                "filename": file_name,
                                "url": file_url,
                                "local_path": local_path
                            })
                    except:
                        continue
            except:
                pass
        
        # 画像の検出とダウンロード
        try:
            fresh_msg = get_fresh_element()
            images = fresh_msg.find_elements(By.CSS_SELECTOR, "img[src*='storage.chatwork.com'], img[src*='appdata.chatwork.com']")
            for i, img in enumerate(images):
                try:
                    img_url = img.get_attribute("src")
                    alt_text = img.get_attribute("alt")
                    
                    # アバター画像は除外
                    if img_url and 'avatar' not in img_url and 'ico_default' not in img_url:
                        img_name = alt_text or f"image_{data['message_id']}_{i}.jpg"
                        local_path = download_file(session, img_url, download_dir, img_name)
                        
                        data["attachments"].append({
                            "type": "image",
                            "filename": img_name,
                            "url": img_url,
                            "local_path": local_path
                        })
                except:
                    continue
        except:
            pass
        
        # タスク判定
        try:
            fresh_msg = get_fresh_element()
            fresh_msg.find_element(By.CSS_SELECTOR, "[data-test='task-icon'], .taskIcon, [class*='task']")
            data["is_task"] = True
        except:
            pass
        
    except Exception as e:
        print(f"  ⚠️  メッセージ解析エラー (mid:{data['message_id']}): {e}")
    
    return data

def export_room_messages(driver, room_url, session, base_download_dir):
    """特定ルームの全メッセージを取得"""
    driver.get(room_url)
    time.sleep(4)
    
    room_id = room_url.split("rid")[-1]
    room_name = f"Room_{room_id}"
    
    room_name_selectors = [
        ".chatRoomHeader__roomTitle",
        "span.chatRoomHeader__roomTitle",
        "._roomName",
        ".room_name",
        "[data-test='room-name']",
        "[data-testid='room-name']",
        "h1[class*='room']"
    ]
    
    try:
        for selector in room_name_selectors:
            try:
                room_name_elem = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                name = room_name_elem.text.strip()
                if name:
                    room_name = name
                    break
            except:
                continue
        
        print(f"\n📁 ルーム: {room_name} (ID: {room_id})")
    
    except Exception as e:
        print(f"\n📁 ルーム: {room_name} (ID: {room_id})")
        print(f"  ⚠️ ルーム名取得失敗: {e}")
    
    safe_room_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_name)
    safe_room_name = safe_room_name.strip()[:50]
    
    download_dir = Path(base_download_dir) / f"{room_id}_{safe_room_name}"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    scroll_to_load_all_messages(driver)
    
    # スクロール後にセッションを更新
    print("  🔄 データ取得前にセッション更新...")
    session = get_session_cookies(driver)
    
    message_selectors = [
        "div[data-mid]",
        "li[data-mid]",
        "[data-test='message-item']"
    ]
    
    messages = []
    for selector in message_selectors:
        messages = driver.find_elements(By.CSS_SELECTOR, selector)
        if messages:
            print(f"  {len(messages)}件のメッセージを検出")
            break
    
    if not messages:
        print("❌ メッセージが見つかりません")
        return None
    
    print(f"📥 メッセージとファイルを処理中...")
    
    extracted_messages = []
    message_refresh_interval = 100  # 100件ごとにセッション更新
    
    for i, msg in enumerate(messages, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(messages)} 件処理完了...")
        
        # 定期的にセッション更新
        if i > 0 and i % message_refresh_interval == 0:
            print(f"  🔄 処理中断防止のためセッション更新...")
            session = get_session_cookies(driver)
        
        data = extract_message_data(msg, session, download_dir)
        extracted_messages.append(data)
    
    return {
        "room_name": room_name,
        "room_id": room_id,
        "room_url": room_url,
        "export_date": datetime.now().isoformat(),
        "total_messages": len(extracted_messages),
        "download_directory": str(download_dir),
        "messages": extracted_messages
    }

def main():
    BASE_DOWNLOAD_DIR = "chatwork_backup"
    Path(BASE_DOWNLOAD_DIR).mkdir(exist_ok=True)
    
    print("\n" + "="*60)
    print("🎯 Chatwork 特定ルームバックアップツール")
    print("="*60)
    print(f"対象キーワード: {', '.join(TARGET_KEYWORDS)}")
    print("="*60 + "\n")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        login_chatwork(driver)
        session = get_session_cookies(driver)
        room_urls = get_all_room_urls(driver)
        
        if not room_urls:
            print("❌ 対象ルームが見つかりませんでした")
            return
        
        all_exports = []
        processed_count = 0
        
        for i, room_url in enumerate(room_urls, 1):
            print(f"\n{'='*60}")
            print(f"ルーム {i}/{len(room_urls)} を処理中")
            print(f"{'='*60}")
            
            # 各ルーム処理前にセッション更新
            if processed_count > 0:
                print("🔄 次のルームへ移動前にセッション更新...")
                refresh_session(driver)
            
            room_data = export_room_messages(driver, room_url, session, BASE_DOWNLOAD_DIR)
            
            if room_data:
                all_exports.append(room_data)
                processed_count += 1
                
                safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_data['room_name'])
                safe_name = safe_name.strip()[:50]
                
                filename = Path(BASE_DOWNLOAD_DIR) / f"{room_data['room_id']}_{safe_name}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(room_data, f, ensure_ascii=False, indent=2)
                
                print(f"✅ {filename.name} に保存しました")
            
            time.sleep(3)
        
        master_filename = Path(BASE_DOWNLOAD_DIR) / f"_all_rooms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(master_filename, "w", encoding="utf-8") as f:
            json.dump(all_exports, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*60}")
        print(f"✅ 全ルームのエクスポート完了")
        print(f"   統合ファイル: {master_filename}")
        print(f"   ダウンロード先: {BASE_DOWNLOAD_DIR}/")
        print(f"   処理ルーム数: {len(all_exports)}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nブラウザを閉じます...")
        driver.quit()

if __name__ == "__main__":
    main()
