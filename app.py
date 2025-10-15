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
import re

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
    
    # User-Agentも設定
    session.headers.update({
        'User-Agent': driver.execute_script("return navigator.userAgent;"),
        'Referer': 'https://www.chatwork.com/'
    })
    
    return session

def download_file_from_chatwork(session, file_url, filename, save_dir):
    """Chatworkからファイルをダウンロード（相対パス対応）"""
    try:
        # 相対パスを絶対パスに変換
        if file_url.startswith('gateway/'):
            file_url = f"https://www.chatwork.com/{file_url}"
        
        # ファイル名をサニタイズ（Windowsで使えない文字を除去）
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        save_path = Path(save_dir) / safe_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        response = session.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # 絶対パスを返す
        absolute_path = str(save_path.resolve())
        print(f"    ✓ ダウンロード: {safe_filename}")
        return absolute_path
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
    
    print(f"  スクロール開始（最大{max_attempts}回試行）...")
    
    for i in range(max_attempts):
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

def extract_message_data(msg, session, download_dir):
    """個別メッセージからデータを抽出（画像・ファイル・フォルダ完全対応）"""
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
        
        # 送信者名
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
        
        # 会社名
        try:
            company_elem = msg.find_element(By.CSS_SELECTOR, ".sc-fjhLSj")
            data["company"] = company_elem.text.strip()
        except:
            pass
        
        # メッセージ本文
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
        
        # タイムスタンプ
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
        
        # ★★★ 1. 画像プレビューの検出（data-file-id対応）★★★
        try:
            preview_images = msg.find_elements(By.CSS_SELECTOR, "img[data-file-id]._filePreview")
            
            for i, img in enumerate(preview_images):
                file_id = img.get_attribute("data-file-id")
                src = img.get_attribute("src")
                
                print(f"    🖼️ 画像プレビュー検出: file_id={file_id}")
                
                # ファイル名を生成
                filename = f"image_{data['message_id']}_{file_id}.jpg"
                
                # 相対パスを絶対URLに変換
                if src and src.startswith('gateway/'):
                    src = f"https://www.chatwork.com/{src}"
                
                # ダウンロード
                local_path = download_file_from_chatwork(session, src, filename, download_dir)
                
                if local_path:
                    data["attachments"].append({
                        "type": "image_preview",
                        "file_id": file_id,
                        "filename": filename,
                        "chatwork_url": src,
                        "local_absolute_path": local_path
                    })
        except Exception as e:
            print(f"    ⚠️ 画像プレビュー取得エラー: {e}")
        
        # ★★★ 2. ファイルダウンロードリンクの検出 ★★★
        # パターン: <a href="gateway/download_file.php?bin=1&file_id=xxx&preview=0">filename.docx (217.83 KB)</a>
        try:
            # data-cwopen属性を持つdiv内のaタグを探す
            file_links = msg.find_elements(By.CSS_SELECTOR, "div[data-cwopen*='download'] a[href*='gateway/download_file.php']")
            
            for link in file_links:
                href = link.get_attribute("href")
                link_text = link.text.strip()
                
                # file_idを抽出
                file_id_match = re.search(r'file_id=(\d+)', href)
                file_id = file_id_match.group(1) if file_id_match else "unknown"
                
                # ファイル名とサイズを分離（例: "filename.docx (217.83 KB)"）
                filename_match = re.match(r'(.+?)\s*\([\d.]+\s*[KMGT]?B\)', link_text)
                if filename_match:
                    filename = filename_match.group(1).strip()
                else:
                    filename = link_text or f"file_{file_id}"
                
                print(f"    📎 ファイル検出: {filename} (file_id={file_id})")
                
                # 相対パスを絶対URLに変換
                if href.startswith('gateway/'):
                    href = f"https://www.chatwork.com/{href}"
                
                # ダウンロード
                local_path = download_file_from_chatwork(session, href, filename, download_dir)
                
                if local_path:
                    data["attachments"].append({
                        "type": "file",
                        "file_id": file_id,
                        "filename": filename,
                        "chatwork_url": href,
                        "local_absolute_path": local_path
                    })
        except Exception as e:
            print(f"    ⚠️ ファイルリンク取得エラー: {e}")
        
        # ★★★ 3. フォルダ（storage.chatwork.com）の検出 ★★★
        try:
            storage_links = msg.find_elements(By.CSS_SELECTOR, "a[href*='storage.chatwork.com']")
            
            for link in storage_links:
                href = link.get_attribute("href")
                link_text = link.text.strip()
                title = link.get_attribute("title")
                download_attr = link.get_attribute("download")
                
                # アバター画像を除外
                if 'avatar' in href or 'ico_default' in href:
                    continue
                
                # ファイル名を取得（優先順位: download属性 > title > リンクテキスト）
                filename = download_attr or title or link_text
                
                # ファイル名がない場合はURLから生成
                if not filename or filename == "":
                    filename = f"storage_file_{data['message_id']}"
                    # URLから拡張子を推測
                    if '.png' in href or '.jpg' in href or '.jpeg' in href:
                        filename += '.jpg'
                    elif '.pdf' in href:
                        filename += '.pdf'
                    elif '.xlsx' in href or '.xls' in href:
                        filename += '.xlsx'
                    elif '.docx' in href:
                        filename += '.docx'
                
                print(f"    📁 ストレージファイル検出: {filename}")
                
                # ダウンロード
                local_path = download_file_from_chatwork(session, href, filename, download_dir)
                
                if local_path:
                    data["attachments"].append({
                        "type": "storage_file",
                        "filename": filename,
                        "chatwork_url": href,
                        "local_absolute_path": local_path
                    })
        except Exception as e:
            print(f"    ⚠️ ストレージファイル取得エラー: {e}")
        
        # タスク判定
        try:
            msg.find_element(By.CSS_SELECTOR, "[data-test='task-icon'], .taskIcon, [class*='task']")
            data["is_task"] = True
        except:
            pass
        
    except Exception as e:
        print(f"  ⚠️  メッセージ解析エラー: {e}")
        import traceback
        traceback.print_exc()
    
    return data

def export_room_messages(driver, room_url, session, base_download_dir):
    """特定ルームの全メッセージを取得"""
    driver.get(room_url)
    time.sleep(4)
    
    room_id = room_url.split("rid")[-1]
    room_name = f"Room_{room_id}"
    
    # ルーム名を取得
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
    
    # ファイル名用に安全な文字列に変換
    safe_room_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_name)
    safe_room_name = safe_room_name.strip()[:50]
    
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
        "download_directory": str(download_dir.resolve()),
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
        print(f"   統合ファイル: {master_filename.resolve()}")
        print(f"   ダウンロード先: {Path(BASE_DOWNLOAD_DIR).resolve()}/")
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
