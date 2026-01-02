import time
import os 
import re 
import msvcrt 
import threading
import random
from queue import Queue, Empty
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

# --- BIẾN TOÀN CỤC CHO ĐA LUỒNG ---
link_queue = Queue()          # Hàng đợi chứa các truyện cần nhúng
stop_event = threading.Event() # Cờ báo hiệu dừng chương trình
file_lock = threading.Lock()   # Khóa để ghi file an toàn
print_lock = threading.Lock()  # Khóa để in màn hình không bị lộn xộn

# --- BIẾN TOÀN CỤC LƯU DRIVER (PROFILE) ---
global_scanner_driver = None
global_embedder_driver = None

def synchronized_print(text):
    with print_lock:
        print(text)

def setup_driver(position=None):
    """
    Khởi tạo trình duyệt.
    """
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    options.set_capability("pageLoadStrategy", "eager")
    
    # Đặt kích thước cửa sổ vừa phải để chạy song song 2 cái
    options.add_argument("--window-size=960,1000")
    
    if position:
        options.add_argument(f"--window-position={position[0]},{position[1]}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.set_page_load_timeout(30) 
    driver.set_script_timeout(30)
    return driver

def get_active_driver(driver_ref, position):
    try:
        _ = driver_ref.title
        return driver_ref
    except:
        return setup_driver(position)

def close_all_drivers():
    global global_scanner_driver, global_embedder_driver
    print("[System] Đang đóng các trình duyệt...")
    if global_scanner_driver:
        try: global_scanner_driver.quit()
        except: pass
    if global_embedder_driver:
        try: global_embedder_driver.quit()
        except: pass

def get_book_id(url):
    if not url: return None
    match_fanqie = re.search(r'/page/(\d+)', url)
    if match_fanqie: return match_fanqie.group(1)
    match_jjwxc = re.search(r'novelid=(\d+)', url)
    if match_jjwxc: return match_jjwxc.group(1)
    match_qimao = re.search(r'/shuku/(\d+)', url)
    if match_qimao: return match_qimao.group(1)
    match_ciweimao = re.search(r'/book/(\d+)', url)
    if match_ciweimao: return match_ciweimao.group(1)
    match_sfacg = re.search(r'/Novel/(\d+)/', url)
    if match_sfacg: return match_sfacg.group(1)
    match_69shu = re.search(r'/(?:book|txt)/(\d+)\.htm', url)
    if match_69shu: return match_69shu.group(1)
    match_quanben5 = re.search(r'/n/([^/]+)/?', url)
    if match_quanben5: return match_quanben5.group(1)
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
    with file_lock:
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(book_id + "\n")
        except: pass

def check_is_recent(text_content):
    if not text_content: return True 
    if any(k in text_content for k in ["刚刚", "分钟", "小时", "今天", "Just now", "minutes", "hours", "Today", "昨天", "前天", "Yesterday"]):
        return True
    
    day_match = re.search(r'(\d+)\s*(天前|days ago)', text_content)
    if day_match: return int(day_match.group(1)) <= 2

    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text_content)
    if date_match:
        try:
            date_obj = datetime.strptime(date_match.group(0), "%Y-%m-%d")
            return (datetime.now() - date_obj).days <= 2
        except: pass
    
    date_match_short = re.search(r'(\d{1,2})-(\d{1,2})', text_content)
    if date_match_short:
        try:
            current_year = datetime.now().year
            date_str = f"{current_year}-{date_match_short.group(1)}-{date_match_short.group(2)}"
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if date_obj > datetime.now(): date_obj = date_obj.replace(year=current_year - 1)
            return (datetime.now() - date_obj).days <= 2
        except: pass

    return True

# --- THREAD 1: NHÚNG TRUYỆN (CONSUMER) ---
def embedder_thread(processed_ids, is_fast_mode=False):
    """
    Luồng chuyên nhúng truyện vào Sangtacviet.
    is_fast_mode: True cho Menu 1 & 8 (Fanqie) -> Tốc độ tối đa
    """
    global global_embedder_driver
    
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(960, 0))
    driver = global_embedder_driver
    
    # Biến đếm số lượng đã nhúng thành công trong phiên chạy này
    session_success_count = 0

    try:
        wait = WebDriverWait(driver, 10)
        
        if "sangtacviet.app" not in driver.current_url:
            synchronized_print("[Embedder] Đang vào Sangtacviet...")
            try:
                driver.get(SANGTACVIET_URL)
                try:
                    login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
                    login_btn.click()
                    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(STV_USERNAME)
                    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(STV_PASSWORD)
                    submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
                    if not submit: submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
                    submit.click()
                    time.sleep(2)
                except: pass 
            except Exception as e:
                synchronized_print(f"[Embedder] Lỗi truy cập STV: {e}")

        while True:
            if stop_event.is_set() and link_queue.empty():
                synchronized_print("[Embedder] Đã xử lý hết hàng tồn. Dừng.")
                break

            try:
                task = link_queue.get(timeout=1)
                book_id, link = task
                
                if book_id in processed_ids:
                    link_queue.task_done()
                    continue

                # synchronized_print(f"-> [Nhúng] ID: {book_id}") # Bỏ bớt in log cho nhanh
                
                for attempt in range(2): 
                    try:
                        # === LOGIC TỐC ĐỘ BÀN THỜ (FAST MODE) ===
                        if is_fast_mode:
                            # 1. Chống 1015: Check Title nhanh
                            if "Attention" in driver.title:
                                synchronized_print("\n[!!!] BỊ CHẶN 1015. NGỦ ĐÔNG 60s...")
                                time.sleep(60)
                                driver.get(SANGTACVIET_URL)
                                time.sleep(3)
                            
                            # 2. Tìm ô input (Timeout cực ngắn)
                            driver.set_page_load_timeout(5)
                            search_box = None
                            try:
                                search_box = driver.find_element(By.TAG_NAME, "input")
                            except:
                                driver.get(SANGTACVIET_URL)
                                search_box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                            
                            # 3. Thao tác nhúng (TỐI ƯU)
                            search_box.clear()
                            
                            # Dán link và Enter ngay lập tức (KHÔNG WAIT)
                            search_box.send_keys(link)
                            search_box.send_keys(Keys.ENTER)
                            
                            # Nghỉ siêu ngắn để server kịp nhận lệnh
                            time.sleep(0.1) 
                            
                            save_history(book_id)
                            processed_ids.add(book_id)
                            session_success_count += 1
                            
                            # Lấy số lượng hàng chờ hiện tại
                            current_qsize = link_queue.qsize()
                            synchronized_print(f"   [OK #{session_success_count}] {book_id} (Fast) | Chờ: {current_qsize}")
                            
                            # Tùy chỉnh tốc độ: Giảm xuống 0.25s theo yêu cầu
                            time.sleep(0.25) 
                            break

                        # === LOGIC THƯỜNG ===
                        else:
                            driver.set_page_load_timeout(10)
                            search_box = None
                            try:
                                search_box = driver.find_element(By.TAG_NAME, "input")
                            except:
                                driver.get(SANGTACVIET_URL)
                                search_box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "input")))

                            search_box.clear()
                            try:
                                search_box.send_keys(Keys.CONTROL + "a")
                                search_box.send_keys(Keys.DELETE)
                            except: pass
                            search_box.send_keys(link)
                            search_box.send_keys(Keys.ENTER)
                            
                            time.sleep(0.5) 
                            try: driver.get(SANGTACVIET_URL)
                            except: pass
                            
                            save_history(book_id)
                            processed_ids.add(book_id)
                            session_success_count += 1
                            current_qsize = link_queue.qsize()
                            synchronized_print(f"   [OK #{session_success_count}] {book_id} | Chờ: {current_qsize}")
                            break
                    
                    except Exception as e:
                        if is_fast_mode:
                             if "Attention" in str(e):
                                synchronized_print("\n[!!!] Lỗi 1015. Ngủ 60s...")
                                time.sleep(60)
                        try: 
                            if len(driver.window_handles) > 1: driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            driver.get(SANGTACVIET_URL)
                        except: pass
                        time.sleep(1)

                link_queue.task_done()
            
            except Empty:
                continue
            except Exception as e:
                synchronized_print(f"[Embedder] Lỗi vòng lặp: {e}")

    except Exception as e:
        synchronized_print(f"[Embedder] Crash: {e}")
    finally:
        synchronized_print("[Embedder] Đã dừng chờ lệnh mới.")

# --- THREAD 2: QUÉT LINK (PRODUCER) ---
def scanner_thread(custom_url, source_type, processed_ids, loop_range=None):
    """Luồng chuyên đi quét link từ các nguồn"""
    global global_scanner_driver
    
    global_scanner_driver = get_active_driver(global_scanner_driver, position=(0, 0))
    driver = global_scanner_driver
    
    try:
        url_template = None
        current_page = 1
        single_page_mode = False 

        # Xử lý URL Template
        if source_type == "jjwxc":
            match = re.search(r'page=(\d+)', custom_url)
            if match:
                current_page = int(match.group(1))
                url_template = custom_url.replace(f"page={current_page}", "page={}")
            else: single_page_mode = True
        elif source_type == "qimao":
            match = re.search(r'-(\d+)/?$', custom_url)
            if match:
                current_page = int(match.group(1))
                prefix = custom_url[:match.start(1)]
                suffix = custom_url[match.end(1):]
                url_template = f"{prefix}{{}}{suffix}"
            else: single_page_mode = True
        elif source_type == "ciweimao":
            match = re.search(r'/(\d+)/?$', custom_url)
            if match:
                current_page = int(match.group(1))
                url_template = custom_url[:match.start(1)] + "/{}" + custom_url[match.end(1):]
            else: single_page_mode = True
        elif source_type == "sfacg":
            match = re.search(r'PageIndex=(\d+)', custom_url, re.IGNORECASE)
            if match:
                current_page = int(match.group(1))
                url_template = re.sub(r'PageIndex=\d+', 'PageIndex={}', custom_url, flags=re.IGNORECASE)
            else: single_page_mode = True
        elif source_type == "69shu":
            single_page_mode = True
            print("[*] 69shu Mode: Chạy 1 trang duy nhất.")
        elif source_type == "quanben5":
            match = re.search(r'_(\d+)\.html', custom_url)
            if match:
                current_page = int(match.group(1))
                url_template = custom_url.replace(f"_{current_page}.html", "_{}.html")
            elif custom_url.endswith(".html"):
                current_page = 1
                url_template = custom_url[:-5] + "_{}.html"
            else:
                single_page_mode = True
        else: # Fanqie
            match = re.search(r'page_(\d+)', custom_url)
            if match:
                current_page = int(match.group(1)) 
                url_template = custom_url.replace(f"page_{current_page}", "page_{}")
            else: single_page_mode = True

        local_queue_cache = [] 

        # Nếu có loop_range (cho menu 8), ghi đè current_page
        if loop_range:
            current_page = loop_range[0]
            print(f"[*] Loop Mode Activated: {loop_range[0]} -> {loop_range[1]}")

        while not stop_event.is_set():
            if single_page_mode: 
                target_url = custom_url
            else: 
                if source_type == "quanben5" and current_page == 1:
                    if "_{}" in url_template:
                        target_url = url_template.replace("_{}.html", ".html")
                    else: target_url = custom_url
                else:
                    target_url = url_template.format(current_page)

            synchronized_print(f"\n[Scanner] Đang quét trang {current_page if not single_page_mode else 'Custom'}...")
            
            try:
                driver.set_page_load_timeout(30)
                driver.get(target_url)
                
                time.sleep(0.5)
                
                if source_type in ["fanqie", "qimao", "ciweimao", "sfacg"]:
                    for _ in range(SCROLL_TIMES):
                        if stop_event.is_set(): break
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.5)

                if stop_event.is_set(): break

                # Tìm element
                elems = []
                if source_type == "fanqie": elems = driver.find_elements(By.CSS_SELECTOR, "a[href^='/page/']")
                elif source_type == "jjwxc": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='onebook.php?novelid=']")
                elif source_type == "qimao": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/shuku/']")
                elif source_type == "ciweimao": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/book/']")
                elif source_type == "sfacg": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/Novel/']")
                elif source_type == "69shu": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/book/'], a[href*='/txt/']")
                elif source_type == "quanben5": elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/n/']")

                found_new_on_page = False
                
                for elem in elems:
                    if stop_event.is_set(): break
                    raw_href = elem.get_attribute('href')
                    if not raw_href: continue
                    
                    # Validate
                    is_valid = False
                    if source_type == "fanqie" and "fanqienovel.com/page/" in raw_href: is_valid = True
                    elif source_type == "jjwxc" and "novelid=" in raw_href and "chapterid=" not in raw_href: is_valid = True
                    elif source_type == "qimao" and "/shuku/" in raw_href and re.search(r'/shuku/\d+/?$', raw_href): is_valid = True
                    elif source_type == "ciweimao" and "/book/" in raw_href and re.search(r'/book/\d+/?$', raw_href): is_valid = True
                    elif source_type == "sfacg" and "/Novel/" in raw_href and re.search(r'/Novel/\d+/?$', raw_href): is_valid = True
                    elif source_type == "69shu" and (".htm" in raw_href): is_valid = True
                    elif source_type == "quanben5" and "/n/" in raw_href: is_valid = True
                    
                    if is_valid:
                        book_id = get_book_id(raw_href)
                        if book_id and book_id not in processed_ids and book_id not in local_queue_cache:
                            # Check ngày
                            book_text = ""
                            try:
                                if source_type == "jjwxc": book_text = elem.find_element(By.XPATH, "./ancestor::tr").text
                                else: book_text = elem.find_element(By.XPATH, "./../..").text
                            except: book_text = elem.text 
                            
                            if check_is_recent(book_text):
                                link_queue.put((book_id, raw_href))
                                local_queue_cache.append(book_id)
                                found_new_on_page = True
                                synchronized_print(f"   [Scanner] +1 Truyện mới: {book_id}")
                            elif source_type == "fanqie" and "sort=newest" in target_url:
                                synchronized_print("[Scanner] Gặp truyện cũ. Dừng quét.")
                                stop_event.set()
                                break

                if not found_new_on_page:
                    synchronized_print(f"[Scanner] Không có truyện mới ở trang {current_page}.")
                    if single_page_mode: 
                        stop_event.set()
                        break
                
                if single_page_mode: 
                    stop_event.set()
                    break
                
                current_page += 1
                
                if loop_range:
                    if current_page > loop_range[1]:
                        print(f"\n[LOOP] Đã xong trang {loop_range[1]}. Quay lại trang {loop_range[0]}...")
                        current_page = loop_range[0]
                else:
                    if current_page > 1000: current_page = 1

            except Exception as e:
                synchronized_print(f"[Scanner] Lỗi quét: {e}")
                time.sleep(3)

    except Exception as e:
        synchronized_print(f"[Scanner] Crash: {e}")
    finally:
        stop_event.set() 
        synchronized_print("[Scanner] Đã dừng.")

def run_concurrent_mode(custom_url, source_type, loop_range=None, is_fast_mode=False):
    processed_ids = load_history()
    print(f"\n[*] Đang khởi động chế độ SONG SONG (2 Trình duyệt)...")
    if loop_range:
        print(f"[*] Chế độ Loop: {loop_range[0]} -> {loop_range[1]}")
    if is_fast_mode:
        print(f"[*] CHẾ ĐỘ FAST (0.25s) & ANTI-1015 ĐƯỢC KÍCH HOẠT.")
    
    print(f"[*] Nhấn phím 'q' để DỪNG Scanner (Embedder sẽ chạy nốt phần còn lại).")
    print(f"[*] LƯU Ý: Bấm vào cửa sổ dòng lệnh (CMD) trước khi ấn 'q'.")
    
    stop_event.clear()
    with link_queue.mutex:
        link_queue.queue.clear()
    
    # Truyền is_fast_mode vào embedder
    t_embedder = threading.Thread(target=embedder_thread, args=(processed_ids, is_fast_mode))
    t_scanner = threading.Thread(target=scanner_thread, args=(custom_url, source_type, processed_ids, loop_range))
    
    t_embedder.start()
    time.sleep(2) 
    t_scanner.start()
    
    while t_scanner.is_alive() or t_embedder.is_alive():
        if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
            print("\n[!!!] NHẬN LỆNH DỪNG: Scanner dừng ngay, Embedder chạy nốt hàng đợi...")
            stop_event.set()
            time.sleep(1)
            
        time.sleep(0.5)
        
        if stop_event.is_set() or (not t_scanner.is_alive() and link_queue.empty()):
            stop_event.set() 
            break

    print("[Main] Đang đợi các luồng về trạng thái nghỉ...")
    t_scanner.join()
    t_embedder.join()
    print("[Main] Đã dừng. (Chrome vẫn mở để bạn dùng tiếp).")

def open_both_browsers_only():
    global global_scanner_driver, global_embedder_driver
    print("\n[*] Đang khởi động/kiểm tra 2 trình duyệt...")
    print("   -> Scanner Driver (Trái)...")
    global_scanner_driver = get_active_driver(global_scanner_driver, position=(0, 0))
    try:
        if "data:," in global_scanner_driver.current_url:
             global_scanner_driver.get("about:blank")
    except: pass

    print("   -> Embedder Driver (Phải)...")
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(960, 0))
    driver = global_embedder_driver
    print("   -> Đang vào Sangtacviet...")
    try:
        driver.get(SANGTACVIET_URL)
        try:
            wait = WebDriverWait(driver, 5)
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
            login_btn.click()
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(STV_USERNAME)
            driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(STV_PASSWORD)
            submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
            if not submit: submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
            submit.click()
            print(f"      + Đã gửi đăng nhập: {STV_USERNAME}")
        except:
            print("      + Đã sẵn sàng (Đã đăng nhập/Không thấy nút).")
    except Exception as e:
        print(f"      ! Lỗi STV: {e}")

    print("\n[OK] 2 Trình duyệt đã mở và sẵn sàng.")
    input("-> Nhấn Enter để quay về Menu chính (Trình duyệt vẫn mở)...")

def main():
    ensure_history_dir()
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n================== 🤖 AUTO NHÚNG TRUYỆN SONG SONG 🤖 ==================")
        print("   [ Chế độ: 2 Trình duyệt - Giữ Profile - Tốc độ cao ]")
        print("-----------------------------------------------------------------------")
        print("   1. 🍅 Chạy nguồn Fanqie (Cà Chua) [FAST+ANTI-1015]")
        print("   2. 🌿 Chạy nguồn Jjwxc (Tấn Giang)")
        print("   3. 🐱 Chạy nguồn Qimao (Thất Miêu)")
        print("   4. 🦔 Chạy nguồn Ciweimao (Thất Vĩ Miêu)")
        print("   5. 🍍 Chạy nguồn SFACG (B菠萝包)")
        print("   6. 📖 Chạy nguồn 69shu (Lục Cửu)")
        print("   7. 📚 Chạy nguồn Quanben5 (Toàn Bản 5)")
        print("   8. ♾️  Chạy Fanqie (Loop 700 -> 3000) [FAST+ANTI-1015]")
        print("-----------------------------------------------------------------------")
        print("   9. 🖥️  Mở 2 Trình duyệt (Scanner & Embedder) để treo")
        print("   10. 📊 Xem tổng số ID đã làm")
        print("   0.  ❌ Thoát (Đóng tất cả)")
        print("=======================================================================")
        
        choice = input("👉 Chọn chức năng (0-10): ").strip()
        
        url = None
        stype = None
        loop_cfg = None
        fast_mode = False 
        
        if choice == '1':
            url = input("\n🔗 Nhập Link Fanqie: ").strip()
            stype = "fanqie"
            fast_mode = True # KÍCH HOẠT FAST MODE CHO MENU 1
        elif choice == '2':
            url = input("\n🔗 Nhập Link Jjwxc: ").strip()
            stype = "jjwxc"
        elif choice == '3':
            url = input("\n🔗 Nhập Link Qimao: ").strip()
            stype = "qimao"
        elif choice == '4':
            url = input("\n🔗 Nhập Link Ciweimao: ").strip()
            stype = "ciweimao"
        elif choice == '5':
            url = input("\n🔗 Nhập Link SFACG: ").strip()
            stype = "sfacg"
        elif choice == '6':
            print("\n🔗 Nhập Link 69shu:")
            print("   Ví dụ: https://www.69shuba.com/novels/class/0.htm")
            url = input("   Link: ").strip()
            stype = "69shu"
        elif choice == '7':
            print("\n🔗 Nhập Link Quanben5:")
            print("   Ví dụ: https://big5.quanben5.com/category/1.html")
            url = input("   Link: ").strip()
            stype = "quanben5"
        elif choice == '8':
            url = "https://fanqienovel.com/library/audience1-cat2-19-stat1-count0/page_700?sort=newest"
            stype = "fanqie"
            loop_cfg = (700, 3000)
            fast_mode = True # KÍCH HOẠT FAST MODE CHO MENU 8
        elif choice == '9':
            open_both_browsers_only()
        elif choice == '10':
            current_ids = load_history()
            print(f"\n[INFO] Tổng số truyện (ID) đã lưu trong file: {len(current_ids)}")
            print(f"File lưu tại: {HISTORY_FILE}")
            input("\n-> Nhấn Enter để quay lại Menu...")
        elif choice == '0':
            close_all_drivers()
            print("👋 Tạm biệt!")
            break
            
        if url and stype:
            run_concurrent_mode(url, stype, loop_range=loop_cfg, is_fast_mode=fast_mode)
            input("\n-> Enter về Menu...")

if __name__ == "__main__":
    main()