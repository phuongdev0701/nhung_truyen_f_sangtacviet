import time
import os 
import re 
import msvcrt 
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib3.exceptions import ReadTimeoutError
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException

# Cấu hình Mặc định
SANGTACVIET_URL = "https://sangtacviet.app/"
SCROLL_TIMES = 3  

# --- CẤU HÌNH ĐƯỜNG DẪN FILE LỊCH SỬ ---
HISTORY_DIR = r"D:\nhúng truyện fanqie, qidian,qimao"
HISTORY_FILE = os.path.join(HISTORY_DIR, "da_lam_xong.txt")

# --- CẤU HÌNH TÀI KHOẢN ---
STV_USERNAME = "YOUR_USERNAME_HERE" 
STV_PASSWORD = "YOUR_PASSWORD_HERE"

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("detach", True)
    options.set_capability("pageLoadStrategy", "eager")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.set_page_load_timeout(30) 
    driver.set_script_timeout(30)
    return driver

def get_book_id(url):
    if not url: return None
    # ID Fanqie: /page/123456
    match_fanqie = re.search(r'/page/(\d+)', url)
    if match_fanqie: return match_fanqie.group(1)
    
    # ID Jjwxc: novelid=123456
    match_jjwxc = re.search(r'novelid=(\d+)', url)
    if match_jjwxc: return match_jjwxc.group(1)

    # ID Qimao: /shuku/123456/
    match_qimao = re.search(r'/shuku/(\d+)', url)
    if match_qimao: return match_qimao.group(1)

    # ID Ciweimao: /book/100xxxx
    match_ciweimao = re.search(r'/book/(\d+)', url)
    if match_ciweimao: return match_ciweimao.group(1)

    # ID SFACG: /Novel/12345/
    match_sfacg = re.search(r'/Novel/(\d+)/', url)
    if match_sfacg: return match_sfacg.group(1)
    
    return None

def ensure_history_dir():
    if not os.path.exists(HISTORY_DIR):
        try: os.makedirs(HISTORY_DIR)
        except: pass

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    ids = set()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip(): ids.add(line.strip())
    except: pass
    return ids

def save_history(book_id):
    if not book_id: return
    ensure_history_dir()
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(book_id + "\n")
    except: pass

def check_is_recent(text_content):
    """Kiểm tra ngày cập nhật (chủ yếu cho Fanqie)"""
    if not text_content: return True 
    if any(k in text_content for k in ["刚刚", "分钟", "小时", "Just now", "minutes", "hours", "昨天", "前天", "Yesterday"]):
        return True
    
    day_match = re.search(r'(\d+)\s*(天前|days ago)', text_content)
    if day_match:
        return int(day_match.group(1)) <= 2

    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text_content)
    if date_match:
        try:
            date_obj = datetime.strptime(date_match.group(0), "%Y-%m-%d")
            return (datetime.now() - date_obj).days <= 2
        except: pass

    return True

def login_to_stv(driver, wait):
    print("--- Đang truy cập Sangtacviet ---")
    try:
        driver.set_page_load_timeout(30)
        driver.get(SANGTACVIET_URL)
        try:
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
            login_btn.click()
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(STV_USERNAME)
            driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(STV_PASSWORD)
            
            submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
            if not submit: submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
            submit.click()
            print(f"-> Đã gửi đăng nhập: {STV_USERNAME}")
            time.sleep(2)
        except:
            print("-> Đã đăng nhập hoặc không thấy nút.")
    except Exception as e:
        print(f"!! Lỗi login: {e}")

def reset_stv_tab(driver, original_window):
    try:
        if len(driver.window_handles) > 1: driver.close()
    except: pass
    driver.switch_to.window(original_window)
    driver.switch_to.new_window('tab')
    driver.set_page_load_timeout(15) 
    try:
        driver.get(SANGTACVIET_URL)
        return True
    except: return False

def run_automation(driver, wait, custom_url, source_type="fanqie"):
    """
    Hàm chạy auto đa năng.
    source_type: 'fanqie', 'jjwxc', 'qimao', 'ciweimao', 'sfacg'
    """
    processed_ids = load_history()
    print(f"\n[*] Lịch sử: {len(processed_ids)} ID.")

    url_template = None
    current_page = 1
    single_page_mode = False 

    # --- XỬ LÝ URL ---
    if source_type == "jjwxc":
        match = re.search(r'page=(\d+)', custom_url)
        if match:
            current_page = int(match.group(1))
            url_template = custom_url.replace(f"page={current_page}", "page={}")
            print(f"[*] Jjwxc Mode: Bắt đầu từ trang {current_page}...")
        else:
            single_page_mode = True
            print("[*] Jjwxc Mode: Chạy 1 trang duy nhất.")
            
    elif source_type == "qimao":
        match = re.search(r'-(\d+)/?$', custom_url)
        if match:
            current_page = int(match.group(1))
            prefix = custom_url[:match.start(1)]
            suffix = custom_url[match.end(1):]
            url_template = f"{prefix}{{}}{suffix}"
            print(f"[*] Qimao Mode: Bắt đầu từ trang {current_page}...")
        else:
            single_page_mode = True
            print("[*] Qimao Mode: Chạy 1 trang duy nhất.")

    elif source_type == "ciweimao":
        match = re.search(r'/(\d+)/?$', custom_url)
        if match:
            current_page = int(match.group(1))
            url_template = custom_url[:match.start(1)] + "/{}" + custom_url[match.end(1):]
            print(f"[*] Ciweimao Mode: Bắt đầu từ trang {current_page}...")
        else:
            single_page_mode = True
            print("[*] Ciweimao Mode: Chạy 1 trang duy nhất.")

    elif source_type == "sfacg":
        # SFACG URL: ...&PageIndex=2
        match = re.search(r'PageIndex=(\d+)', custom_url, re.IGNORECASE)
        if match:
            current_page = int(match.group(1))
            # Thay thế PageIndex=X bằng PageIndex={}
            url_template = custom_url.replace(f"PageIndex={current_page}", "PageIndex={}")
            # Xử lý trường hợp URL chữ hoa/thường khác nhau nếu cần, nhưng replace chuỗi chuẩn là an toàn nhất
            if url_template == custom_url: # Nếu replace thất bại do case sensitive
                 url_template = re.sub(r'PageIndex=\d+', 'PageIndex={}', custom_url, flags=re.IGNORECASE)
            
            print(f"[*] SFACG Mode: Bắt đầu từ trang {current_page}...")
        else:
            single_page_mode = True
            print("[*] SFACG Mode: Chạy 1 trang duy nhất (Hoặc thiếu PageIndex=X).")
            
    else:
        # Fanqie
        match = re.search(r'page_(\d+)', custom_url)
        if match:
            current_page = int(match.group(1)) 
            url_template = custom_url.replace(f"page_{current_page}", "page_{}")
        else:
            single_page_mode = True

    stop_scan_completely = False 

    while True:
        if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
            print("\n[!!!] Đã nhận lệnh DỪNG.")
            break

        if stop_scan_completely: break

        if single_page_mode: target_url = custom_url
        else: target_url = url_template.format(current_page)

        print(f"\n==================================================")
        print(f"[*] QUÉT TRANG: {current_page} ({source_type.upper()})")
        
        # 1. QUÉT LINK
        new_books = []
        try:
            driver.set_page_load_timeout(20) 
            driver.get(target_url)
            time.sleep(1.5)
            
            # --- LOGIC QUÉT THEO NGUỒN ---
            elems = []
            
            if source_type == "fanqie":
                for i in range(SCROLL_TIMES):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                elems = driver.find_elements(By.CSS_SELECTOR, "a[href^='/page/']")
            
            elif source_type == "jjwxc":
                elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='onebook.php?novelid=']")
            
            elif source_type == "qimao":
                for i in range(SCROLL_TIMES):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/shuku/']")

            elif source_type == "ciweimao":
                for i in range(SCROLL_TIMES):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/book/']")

            elif source_type == "sfacg":
                # SFACG list load khá nhanh, nhưng cứ cuộn cho chắc
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                # Tìm link chứa /Novel/ và số ID
                elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/Novel/']")

            # --- LỌC VÀ LẤY ID ---
            for elem in elems:
                raw_href = elem.get_attribute('href')
                if not raw_href: continue
                
                is_valid = False
                
                if source_type == "fanqie" and "fanqienovel.com/page/" in raw_href: 
                    is_valid = True
                elif source_type == "jjwxc" and "novelid=" in raw_href and "chapterid=" not in raw_href: 
                    is_valid = True
                elif source_type == "qimao":
                    if "qimao.com/shuku/" in raw_href and re.search(r'/shuku/\d+/?$', raw_href):
                        is_valid = True
                elif source_type == "ciweimao":
                    if "ciweimao.com/book/" in raw_href and re.search(r'/book/\d+/?$', raw_href):
                        is_valid = True
                elif source_type == "sfacg":
                    # Link SFACG chuẩn: book.sfacg.com/Novel/12345/
                    if "book.sfacg.com/Novel/" in raw_href and re.search(r'/Novel/\d+/?$', raw_href):
                        is_valid = True
                
                if is_valid:
                    book_id = get_book_id(raw_href)
                    if book_id and book_id not in processed_ids:
                        if not any(item[0] == book_id for item in new_books):
                            # Check ngày Fanqie
                            if source_type == "fanqie":
                                try: book_text = elem.find_element(By.XPATH, "./../..").text
                                except: book_text = elem.text
                                if check_is_recent(book_text): new_books.append((book_id, raw_href))
                                elif "sort=newest" in target_url: stop_scan_completely = True; break
                            else:
                                new_books.append((book_id, raw_href))

        except Exception as e:
            print(f"[!] Lỗi quét link: {e}. Thử lại...")
            time.sleep(2)
            continue

        if not new_books:
            if stop_scan_completely: 
                print("\n[STOP] Đã gặp truyện cũ. Dừng.")
                break
            
            print(f"[!] Không có truyện mới ở trang này.")
            if single_page_mode: break
            else:
                current_page += 1
                if current_page > 1000: current_page = 1
                continue

        print(f"[+] Tìm thấy {len(new_books)} truyện MỚI.")

        # 2. XỬ LÝ SANGTACVIET
        print("=> Bắt đầu nhúng (Nhấn 'q' để DỪNG)...")
        original_window = driver.current_window_handle
        
        # Mở tab STV
        try:
            driver.switch_to.new_window('tab')
            driver.set_page_load_timeout(15)
            driver.get(SANGTACVIET_URL)
        except Exception as e:
            print(f"-> [!] Lỗi mở tab STV: {e}")
            reset_stv_tab(driver, original_window)
        
        stop_requested = False

        for index, (book_id, link) in enumerate(new_books):
            if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
                print("\n[!!!] Đã nhận lệnh DỪNG.")
                stop_requested = True
                break
            
            if book_id in processed_ids: continue

            print(f"ID: {book_id} | ", end='')
            
            try:
                driver.set_page_load_timeout(10)
                driver.set_script_timeout(10)
                
                wait_short = WebDriverWait(driver, 5) 
                
                search_box = wait_short.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                
                search_box.clear()
                try: 
                    search_box.send_keys(Keys.CONTROL + "a")
                    search_box.send_keys(Keys.DELETE)
                except: pass
                
                search_box.send_keys(link)
                search_box.send_keys(Keys.ENTER)
                
                save_history(book_id)
                processed_ids.add(book_id)
                print("OK.")

            except (TimeoutException, ReadTimeoutError, WebDriverException, Exception) as e:
                print(f"Lỗi/Lag -> Reset Tab & SKIP.")
                time.sleep(2)
                reset_stv_tab(driver, original_window)

        try:
            if len(driver.window_handles) > 1: driver.close()
            driver.switch_to.window(original_window)
        except:
            driver.switch_to.window(driver.window_handles[0])
        
        if stop_requested: break
        if stop_scan_completely: break
            
        print(f"\n[DONE] Xong trang {current_page}.")
        
        if single_page_mode: break 
        else: 
            current_page += 1
            if current_page > 1000: current_page = 1

def main():
    driver = None
    wait = None
    ensure_history_dir()

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n================ MENU TOOL NHÚNG TRUYỆN ================")
        print("1. Mở Sangtacviet (Để đăng nhập)")
        print("2. Chạy Auto (Nguồn Fanqie - Nhập Link)")
        print("3. Chạy Auto (Nguồn Jjwxc - Tấn Giang)")
        print("4. Chạy Auto (Nguồn Qimao - Thất Miêu)")
        print("5. Chạy Auto (Nguồn Ciweimao - Thất Vĩ Miêu)")
        print("6. Chạy Auto (Nguồn SFACG - B菠萝包) [MỚI]")
        print("7. Xem tổng số ID đã làm")
        print("8. Thoát")
        print("========================================================")
        
        choice = input("Chọn chức năng (1-8): ").strip()
        
        if choice in ['1', '2', '3', '4', '5', '6']:
            if driver is None:
                print("\n[*] Khởi động Chrome...")
                try:
                    driver = setup_driver()
                    wait = WebDriverWait(driver, 10)
                except Exception as e:
                    print(f"Lỗi: {e}")
                    input("Enter để thử lại...")
                    continue

            if choice == '1':
                login_to_stv(driver, wait)
                input("\n-> Enter về Menu...")
            elif choice == '2':
                lnk = input("\nLink Fanqie: ").strip()
                if lnk: run_automation(driver, wait, custom_url=lnk, source_type="fanqie")
                else: print("Link trống!")
                input("\n-> Enter về Menu...")
            elif choice == '3':
                print("\n--- NHẬP LINK JJWXC ---")
                print("Ví dụ: ...&page=1...")
                lnk = input("Dán link: ").strip()
                if lnk: 
                    run_automation(driver, wait, custom_url=lnk, source_type="jjwxc")
                else:
                    print("Link trống!")
                input("\n-> Enter về Menu...")
            elif choice == '4':
                print("\n--- NHẬP LINK QIMAO ---")
                print("Ví dụ: ...-click-1/")
                lnk = input("Dán link: ").strip()
                if lnk: 
                    run_automation(driver, wait, custom_url=lnk, source_type="qimao")
                else:
                    print("Link trống!")
                input("\n-> Enter về Menu...")
            elif choice == '5':
                print("\n--- NHẬP LINK CIWEIMAO ---")
                print("Ví dụ: .../quanbu/1")
                lnk = input("Dán link: ").strip()
                if lnk: 
                    run_automation(driver, wait, custom_url=lnk, source_type="ciweimao")
                else:
                    print("Link trống!")
                input("\n-> Enter về Menu...")
            elif choice == '6':
                print("\n--- NHẬP LINK SFACG ---")
                print("Ví dụ: https://book.sfacg.com/List/default.aspx?ud=7&PageIndex=2")
                lnk = input("Dán link: ").strip()
                if lnk: 
                    run_automation(driver, wait, custom_url=lnk, source_type="sfacg")
                else:
                    print("Link trống!")
                input("\n-> Enter về Menu...")

        elif choice == '7':
            current_ids = load_history()
            print(f"\n[INFO] Tổng số ID đã lưu: {len(current_ids)}")
            input("\n-> Nhấn Enter để quay lại Menu...")
        
        elif choice == '8':
            if driver: 
                try: driver.quit()
                except: pass
            break
        else: time.sleep(1)

if __name__ == "__main__":
    main()