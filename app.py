from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
import time
import json
import os
import requests
from datetime import datetime
from pathlib import Path
import re

# フィルター対象のキーワード
TARGET_KEYWORDS = [
    "森田"
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
    
    # data-rid からURLとルーム名を取得（Stale対策：即座にデータ抽出）
    room_data = []
    
    if room_elements:
        for elem in room_elements:
            try:
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
            except StaleElementReferenceException:
                # 古い要素になった場合はスキップ
                continue
    
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
                        try:
                            href = link.get_attribute("href")
                            name = link.text.strip() or "Unknown"
                            if href and "rid" in href:
                                rid = href.split("rid")[-1]
                                room_data.append({
                                    "url": href,
                                    "name": name,
                                    "rid": rid
                                })
                        except StaleElementReferenceException:
                            continue
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
    max_attempts = 100
    wait_time = 2.5
    
    print(f"  スクロール開始（最大{max_attempts}回試行）...")
    
    for i in range(max_attempts):
        # 現在のメッセージ数を取得（Stale対策：毎回再取得）
        try:
            messages = driver.find_elements(By.CSS_SELECTOR, "[data-mid]")
            current_count = len(messages)
        except:
            print(f"    ⚠️ メッセージ取得エラー、再試行...")
            time.sleep(1)
            continue
        
        # チャットエリアを再取得（Stale対策）
        try:
            for selector in selectors:
                try:
                    chat_area = driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            driver.execute_script("arguments[0].scrollTop = 0", chat_area)
        except:
            print(f"    ⚠️ スクロールエラー、続行...")
        
        time.sleep(wait_time)
        
        # スクロール後のメッセージ数を再取得
        try:
            messages_after_wait = driver.find_elements(By.CSS_SELECTOR, "[data-mid]")
            count_after_wait = len(messages_after_wait)
        except:
            count_after_wait = current_count
        
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
    
    # 最後に一番上にスクロール
    try:
        for selector in selectors:
            try:
                chat_area = driver.find_element(By.CSS_SELECTOR, selector)
                driver.execute_script("arguments[0].scrollTop = 0", chat_area)
                break
            except:
                continue
    except:
        pass
    
    time.sleep(2)
    
    final_count = len(driver.find_elements(By.CSS_SELECTOR, "[data-mid]"))
    print(f"  📊 最終取得件数: {final_count}件")

def safe_get_text(element, max_retries=3):
    """Stale対策：要素からテキストを安全に取得"""
    for attempt in range(max_retries):
        try:
            return element.text.strip()
        except StaleElementReferenceException:
            if attempt < max_retries - 1:
                time.sleep(0.1)
                continue
            return ""
    return ""

def safe_get_attribute(element, attr_name, max_retries=3):
    """Stale対策：要素から属性を安全に取得"""
    for attempt in range(max_retries):
        try:
            return element.get_attribute(attr_name)
        except StaleElementReferenceException:
            if attempt < max_retries - 1:
                time.sleep(0.1)
                continue
            return None
    return None

def extract_message_data_by_id(driver, message_id, session, download_dir):
    """message_idを使って都度要素を再取得しながらデータ抽出（添付ファイル完全対応）"""
    data = {
        "message_id": message_id,
        "sender": "Unknown",
        "company": "",
        "body": "",
        "timestamp": "",
        "attachments": [],
        "is_task": False
    }
    
    def get_fresh_message():
        """常に最新のメッセージ要素を取得"""
        try:
            return driver.find_element(By.CSS_SELECTOR, f"[data-mid='{message_id}']")
        except NoSuchElementException:
            return None
    
    try:
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
                msg = get_fresh_message()
                if msg:
                    sender = msg.find_element(By.CSS_SELECTOR, selector)
                    sender_text = safe_get_text(sender)
                    if sender_text:
                        data["sender"] = sender_text
                        break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        
        # 会社名・所属
        try:
            msg = get_fresh_message()
            if msg:
                company_elem = msg.find_element(By.CSS_SELECTOR, ".sc-fjhLSj")
                data["company"] = safe_get_text(company_elem)
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
                msg = get_fresh_message()
                if msg:
                    body = msg.find_element(By.CSS_SELECTOR, selector)
                    body_text = safe_get_text(body)
                    if body_text:
                        data["body"] = body_text
                        break
            except (NoSuchElementException, StaleElementReferenceException):
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
                msg = get_fresh_message()
                if msg:
                    time_elem = msg.find_element(By.CSS_SELECTOR, selector)
                    data_tm = safe_get_attribute(time_elem, "data-tm")
                    datetime_attr = safe_get_attribute(time_elem, "datetime")
                    text = safe_get_text(time_elem)
                    
                    if datetime_attr:
                        data["timestamp"] = datetime_attr
                    elif data_tm:
                        data["timestamp"] = f"unix:{data_tm}"
                    elif text:
                        data["timestamp"] = text
                    
                    if data["timestamp"]:
                        break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        
        # ★★★ 1. 画像プレビューの検出（data-file-id対応）★★★
        try:
            msg = get_fresh_message()
            if msg:
                preview_images = msg.find_elements(By.CSS_SELECTOR, "img[data-file-id]._filePreview")
                
                for i, img in enumerate(preview_images):
                    file_id = safe_get_attribute(img, "data-file-id")
                    src = safe_get_attribute(img, "src")
                    
                    if file_id:
                        print(f"    🖼️ 画像プレビュー検出: file_id={file_id}")
                        
                        filename = f"image_{message_id}_{file_id}.jpg"
                        
                        if src and src.startswith('gateway/'):
                            src = f"https://www.chatwork.com/{src}"
                        
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
        try:
            msg = get_fresh_message()
            if msg:
                file_links = msg.find_elements(By.CSS_SELECTOR, "div[data-cwopen*='download'] a[href*='gateway/download_file.php']")
                
                for link in file_links:
                    href = safe_get_attribute(link, "href")
                    link_text = safe_get_text(link)
                    
                    file_id_match = re.search(r'file_id=(\d+)', href) if href else None
                    file_id = file_id_match.group(1) if file_id_match else "unknown"
                    
                    filename_match = re.match(r'(.+?)\s*\([\d.]+\s*[KMGT]?B\)', link_text) if link_text else None
                    if filename_match:
                        filename = filename_match.group(1).strip()
                    else:
                        filename = link_text or f"file_{file_id}"
                    
                    if href:
                        print(f"    📎 ファイル検出: {filename} (file_id={file_id})")
                        
                        if href.startswith('gateway/'):
                            href = f"https://www.chatwork.com/{href}"
                        
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
        
        # ★★★ 3. ストレージファイルの検出 ★★★
        try:
            msg = get_fresh_message()
            if msg:
                storage_links = msg.find_elements(By.CSS_SELECTOR, "a[href*='storage.chatwork.com']")
                
                for link in storage_links:
                    href = safe_get_attribute(link, "href")
                    link_text = safe_get_text(link)
                    title = safe_get_attribute(link, "title")
                    download_attr = safe_get_attribute(link, "download")
                    
                    if href and ('avatar' in href or 'ico_default' in href):
                        continue
                    
                    filename = download_attr or title or link_text
                    
                    if not filename or filename == "":
                        filename = f"storage_file_{message_id}"
                        if href:
                            if '.png' in href or '.jpg' in href or '.jpeg' in href:
                                filename += '.jpg'
                            elif '.pdf' in href:
                                filename += '.pdf'
                            elif '.xlsx' in href or '.xls' in href:
                                filename += '.xlsx'
                            elif '.docx' in href:
                                filename += '.docx'
                    
                    if href:
                        print(f"    📁 ストレージファイル検出: {filename}")
                        
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
            msg = get_fresh_message()
            if msg:
                msg.find_element(By.CSS_SELECTOR, "[data-test='task-icon'], .taskIcon, [class*='task']")
                data["is_task"] = True
        except:
            pass
        
    except Exception as e:
        print(f"  ⚠️  メッセージ解析エラー (mid:{message_id}): {e}")
    
    return data

def export_room_messages(driver, room_url, session, base_download_dir):
    """特定ルームの全メッセージを取得"""
    driver.get(room_url)
    time.sleep(4)
    
    room_id = room_url.split("rid")[-1]
    
    room_name_selectors = [
        ".chatRoomHeader__roomTitle",
        "span.chatRoomHeader__roomTitle",
        "._roomName",
        ".room_name",
        "[data-test='room-name']",
        "[data-testid='room-name']",
        "h1[class*='room']"
    ]
    
    room_name = f"Room_{room_id}"
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
    except:
        pass
    
    print(f"\n📁 ルーム: {room_name} (ID: {room_id})")
    
    safe_room_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_name)
    safe_room_name = safe_room_name.strip()[:50]
    
    download_dir = Path(base_download_dir) / f"{room_id}_{safe_room_name}"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    scroll_to_load_all_messages(driver)
    
    # データ取得用のセッションを準備
    session = get_session_cookies(driver)
    
    # メッセージIDのリストを最初に取得（Stale対策の核心）
    print("  📋 メッセージIDリストを取得中...")
    message_ids = []
    
    message_selectors = [
        "div[data-mid]",
        "li[data-mid]",
        "[data-test='message-item']"
    ]
    
    for selector in message_selectors:
        try:
            messages = driver.find_elements(By.CSS_SELECTOR, selector)
            if messages:
                print(f"  {len(messages)}件のメッセージを検出")
                # IDだけ先に全て抽出（要素参照は保持しない）
                for msg in messages:
                    try:
                        mid = safe_get_attribute(msg, "data-mid")
                        if mid:
                            message_ids.append(mid)
                    except:
                        continue
                break
        except:
            continue
    
    if not message_ids:
        print("❌ メッセージが見つかりません")
        return None
    
    print(f"📥 {len(message_ids)}件のメッセージとファイルを処理中...")
    
    extracted_messages = []
    
    # IDベースで処理（Stale問題を根本解決）
    for i, message_id in enumerate(message_ids, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(message_ids)} 件処理完了...")
        
        # 各メッセージごとに新鮮な要素を取得して処理
        data = extract_message_data_by_id(driver, message_id, session, download_dir)
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
    print("Chatwork 特定ルームバックアップツール")
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
