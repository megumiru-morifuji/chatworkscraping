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
    
    # data-rid からURLを生成
    room_urls = set()
    
    if room_elements:
        for elem in room_elements:
            rid = elem.get_attribute("data-rid")
            if rid:
                # ChatworkのURL形式でURLを生成
                room_url = f"https://www.chatwork.com/#!rid{rid}"
                room_urls.add(room_url)
                
                # ルーム名も取得（デバッグ用）
                try:
                    label = elem.get_attribute("aria-label")
                    if label:
                        print(f"    - {label[:30]} (rid{rid})")
                except:
                    pass
    
    # 旧UIにも対応（念のため）
    if not room_urls:
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
                        if href and "rid" in href:
                            room_urls.add(href)
            except:
                continue
    
    # 手動入力モードへのフォールバック
    if not room_urls:
        print("\n❌ 自動検出できませんでした")
        print("\n📋 手動モード: ルームURLまたはルームIDを入力してください")
        print("   例1: https://www.chatwork.com/#!rid374988330")
        print("   例2: 374988330 (IDのみでもOK)")
        print("   複数ある場合はカンマ区切り、完了したら空行でEnter\n")
        
        manual_urls = []
        while True:
            user_input = input("ルームURL/ID（終了は空Enter）>> ").strip()
            if not user_input:
                break
            
            # カンマ区切りに対応
            for item in user_input.split(','):
                item = item.strip()
                if not item:
                    continue
                
                # URLかIDかを判定
                if 'http' in item or '#!rid' in item:
                    # URL形式
                    if 'rid' in item:
                        manual_urls.append(item)
                else:
                    # ID形式（数字のみ）
                    if item.isdigit():
                        manual_urls.append(f"https://www.chatwork.com/#!rid{item}")
        
        if manual_urls:
            room_urls = set(manual_urls)
            print(f"\n✅ 手動で{len(room_urls)}個のルームを登録しました")
        else:
            print("\n❌ ルームURLが入力されませんでした")
            return []
    
    room_urls = list(room_urls)
    print(f"\n✅ 合計 {len(room_urls)}個のルームを検出しました")
    
    for i, url in enumerate(room_urls[:10], 1):
        print(f"  {i}. {url}")
    if len(room_urls) > 10:
        print(f"  ... 他 {len(room_urls) - 10} 件")
    
    return room_urls

def get_session_cookies(driver):
    """SeleniumのCookieをrequestsセッションに転送"""
    session = requests.Session()
    selenium_cookies = driver.get_cookies()
    
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
    
    return session

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
    """チャット履歴を全て読み込むまでスクロール"""
    print("📜 過去のメッセージを読み込み中...")
    
    # チャットエリアを特定
    chat_area = None
    selectors = [
        "#_chatText",
        ".cw_chat_body",
        "[role='log']",
        ".chatTimeLineContainer",
        "#_timeLine",
        "[class*='timeline']",
        "[class*='messageList']"
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
    max_attempts = 200  # 最大スクロール回数を増やす
    scroll_amount = 1000  # 一度に大きくスクロール
    
    print(f"  スクロール開始（最大{max_attempts}回試行）...")
    
    for i in range(max_attempts):
        # 現在のメッセージ数を取得
        messages = driver.find_elements(By.CSS_SELECTOR, "[data-mid]")
        current_count = len(messages)
        
        # 一番上にスクロール
        driver.execute_script("arguments[0].scrollTop = 0", chat_area)
        time.sleep(1)
        
        # 変化をチェック
        if current_count == previous_message_count:
            no_change_count += 1
            if no_change_count >= 5:  # 5回変化なしで終了
                print(f"  ✅ 全メッセージ読み込み完了 ({current_count}件)")
                break
        else:
            no_change_count = 0
            if i % 10 == 0 or current_count != previous_message_count:
                print(f"    {current_count}件のメッセージを検出中...")
        
        previous_message_count = current_count
        
        # 進捗表示
        if i > 0 and i % 50 == 0:
            print(f"    スクロール継続中... ({i}/{max_attempts}回)")
    
    if no_change_count < 5:
        print(f"  ⚠️ 最大試行回数に達しました ({previous_message_count}件)")
    
    # 最後に一番上にスクロール
    driver.execute_script("arguments[0].scrollTop = 0", chat_area)
    time.sleep(2)

def extract_message_data(msg, session, download_dir):
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
        data["message_id"] = msg.get_attribute("data-mid")
        
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
                sender = msg.find_element(By.CSS_SELECTOR, selector)
                data["sender"] = sender.text.strip()
                if data["sender"]:
                    break
            except:
                continue
        
        # 会社名・所属（新UI）
        try:
            company_elem = msg.find_element(By.CSS_SELECTOR, ".sc-fjhLSj")
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
                body = msg.find_element(By.CSS_SELECTOR, selector)
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
                time_elem = msg.find_element(By.CSS_SELECTOR, selector)
                # data-tm属性（UNIXタイムスタンプ）も取得
                data_tm = time_elem.get_attribute("data-tm")
                datetime_attr = time_elem.get_attribute("datetime")
                text = time_elem.text.strip()
                
                # 優先順位: datetime > data-tm > テキスト
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
                files = msg.find_elements(By.CSS_SELECTOR, selector)
                for file_elem in files:
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
                pass
        
        # 画像の検出とダウンロード
        try:
            images = msg.find_elements(By.CSS_SELECTOR, "img[src*='storage.chatwork.com'], img[src*='appdata.chatwork.com']")
            for i, img in enumerate(images):
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
            pass
        
        # タスク判定
        try:
            msg.find_element(By.CSS_SELECTOR, "[data-test='task-icon'], .taskIcon, [class*='task']")
            data["is_task"] = True
        except:
            pass
        
    except Exception as e:
        print(f"  ⚠️  メッセージ解析エラー: {e}")
    
    return data

def export_room_messages(driver, room_url, session, base_download_dir):
    """特定ルームの全メッセージを取得"""
    driver.get(room_url)
    time.sleep(4)
    
    # ルームIDを取得
    room_id = room_url.split("rid")[-1]
    room_name = f"Room_{room_id}"
    
    # ルーム名を取得（ヘッダー部分から）
    room_name_selectors = [
        ".chatRoomHeader__roomTitle",  # 新UI
        "span.chatRoomHeader__roomTitle",
        "._roomName",
        ".room_name",
        "[data-test='room-name']",
        "[data-testid='room-name']",
        "h1[class*='room']"
    ]
    
    try:
        # ページ上部のヘッダーからルーム名を探す
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
    
    # ファイル名用に安全な文字列に変換
    safe_room_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_name)
    safe_room_name = safe_room_name.strip()[:50]  # 最大50文字
    
    # このルーム専用のダウンロードディレクトリ
    download_dir = Path(base_download_dir) / f"{room_id}_{safe_room_name}"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # 全メッセージを読み込み
    scroll_to_load_all_messages(driver)
    
    # メッセージ要素を取得
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
    for i, msg in enumerate(messages, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(messages)} 件処理完了...")
        
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
    # ダウンロード先ディレクトリ
    BASE_DOWNLOAD_DIR = "chatwork_backup"
    Path(BASE_DOWNLOAD_DIR).mkdir(exist_ok=True)
    
    # Chromeドライバーを起動
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        # ログイン（手動）
        login_chatwork(driver)
        
        # セッションCookieを取得
        session = get_session_cookies(driver)
        
        # 全ルームURLを自動取得
        room_urls = get_all_room_urls(driver)
        
        if not room_urls:
            print("❌ ルームが見つかりませんでした")
            return
        
        # 各ルームのメッセージを取得
        all_exports = []
        for i, room_url in enumerate(room_urls, 1):
            print(f"\n{'='*60}")
            print(f"ルーム {i}/{len(room_urls)} を処理中")
            print(f"{'='*60}")
            
            room_data = export_room_messages(driver, room_url, session, BASE_DOWNLOAD_DIR)
            
            if room_data:
                all_exports.append(room_data)
                
                # ファイル名用に安全な文字列を作成
                safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_data['room_name'])
                safe_name = safe_name.strip()[:50]
                
                # ルームごとに個別保存
                filename = Path(BASE_DOWNLOAD_DIR) / f"{room_data['room_id']}_{safe_name}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(room_data, f, ensure_ascii=False, indent=2)
                
                print(f"✅ {filename.name} に保存しました")
            
            time.sleep(3)
        
        # 全ルームをまとめて保存
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
