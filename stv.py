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

# --- CẤU HÌNH TỐI ƯU ---
SANGTACVIET_URL = "https://sangtacviet.app/"
SCROLL_TIMES = 2  # Giảm số lần cuộn để nhanh hơn
SCROLL_DELAY = 0.2 # Giảm thời gian chờ giữa các lần cuộn

# --- CẤU HÌNH ĐƯỜNG DẪN FILE ---
HISTORY_DIR = r"D:\nhúng truyện fanqie, qidian,qimao"
HISTORY_FILE = os.path.join(HISTORY_DIR, "da_lam_xong.txt")
BATCH_FILE = os.path.join(HISTORY_DIR, "batch_fanqie.txt") 

# --- CẤU HÌNH TÀI KHOẢN ---
STV_USERNAME = "YOUR_USERNAME_HERE" 
STV_PASSWORD = "YOUR_PASSWORD_HERE"

# --- BIẾN TOÀN CỤC ---
link_queue = Queue()       
stop_event = threading.Event() 
file_lock = threading.Lock()   
print_lock = threading.Lock()  

global_scanner_driver = None
global_embedder_driver = None
total_success_count = 0  # Biến đếm tổng, không bị reset khi đổi menu

def synchronized_print(text):
    with print_lock:
        print(text)

def setup_driver(position=None):
    """
    Khởi tạo trình duyệt với cấu hình tối ưu tốc độ.
    """
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    options.set_capability("pageLoadStrategy", "eager") # Load trang không cần đợi full resources
    
    # --- ĐÃ BẬT LẠI ẢNH ĐỂ GIẢI CAPTCHA ---
    # (Dòng chặn ảnh đã được xóa để bạn có thể nhìn thấy CAPTCHA)
    # prefs = {"profile.managed_default_content_settings.images": 2}
    # options.add_experimental_option("prefs", prefs)
    
    options.add_argument("--window-size=800,900") # Giảm kích thước window chút cho nhẹ
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-application-cache")
    
    if position:
        options.add_argument(f"--window-position={position[0]},{position[1]}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.set_page_load_timeout(30) # Tăng timeout lên chút vì giờ load cả ảnh
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

def ensure_dirs_and_files():
    if not os.path.exists(HISTORY_DIR):
        try: os.makedirs(HISTORY_DIR)
        except: pass
    if not os.path.exists(BATCH_FILE):
        try:
            with open(BATCH_FILE, "w", encoding="utf-8") as f:
                f.write("") 
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
    ensure_dirs_and_files()
    with file_lock:
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(book_id + "\n")
        except: pass

def read_batch_file():
    urls = []
    if os.path.exists(BATCH_FILE):
        try:
            with open(BATCH_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    clean_line = line.strip()
                    if clean_line and not clean_line.startswith("#"):
                        urls.append(clean_line)
        except Exception as e:
            synchronized_print(f"[System] Lỗi đọc file batch: {e}")
    return urls

def check_is_recent(text_content):
    if not text_content: return True 
    # Check nhanh bằng từ khóa trước
    if any(k in text_content for k in ["刚刚", "分钟", "小时", "今天", "Just now", "minutes", "hours", "Today", "昨天", "Yesterday"]):
        return True
    
    # Regex check ngày
    day_match = re.search(r'(\d+)\s*(天前|days ago)', text_content)
    if day_match: return int(day_match.group(1)) <= 2

    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text_content)
    if date_match:
        try:
            date_obj = datetime.strptime(date_match.group(0), "%Y-%m-%d")
            return (datetime.now() - date_obj).days <= 2
        except: pass
    
    return True

# --- HELPER: JS FAST INTERACTION ---
def fast_js_type(driver, element, text):
    """Dùng JS để điền value ngay lập tức thay vì gõ từng phím"""
    driver.execute_script("arguments[0].value = arguments[1];", element, text)
    driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)

def fast_js_click(driver, element):
    """Click bằng JS để tránh bị lỗi che khuất"""
    driver.execute_script("arguments[0].click();", element)

# --- THREAD 1: NHÚNG TRUYỆN (CONSUMER) - ĐÃ TỐI ƯU ---
def embedder_thread(processed_ids, is_fast_mode=False):
    global global_embedder_driver, total_success_count
    
    # Đặt vị trí bên phải
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(800, 0))
    driver = global_embedder_driver
    # session_success_count = 0  <-- Xóa dòng này (biến cục bộ cũ)

    try:
        wait = WebDriverWait(driver, 5) # Giảm wait time xuống
        
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
                    submit.click()
                    time.sleep(1)
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

                # --- VÒNG LẶP NHÚNG CỰC NHANH ---
                for attempt in range(2): 
                    try:
                        # Kiểm tra lỗi 1015
                        if "Attention" in driver.title:
                            synchronized_print("\n[!!!] BỊ CHẶN 1015. NGỦ 45s...")
                            time.sleep(45) # Giảm thời gian chờ xuống chút
                            driver.get(SANGTACVIET_URL)
                            time.sleep(2)
                        
                        # TÌM Ô INPUT (Ưu tiên tìm bằng JS hoặc CSS đơn giản nhất)
                        search_box = None
                        try:
                            search_box = driver.find_element(By.TAG_NAME, "input")
                        except:
                            driver.get(SANGTACVIET_URL)
                            search_box = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                        
                        # --- SIÊU TỐC ĐỘ: DÙNG JS ĐỂ ĐIỀN LINK VÀ ENTER ---
                        # Thay vì clear() rồi send_keys() (mất khoảng 0.5-1s), ta dùng JS (0.01s)
                        fast_js_type(driver, search_box, link)
                        
                        # Gửi phím Enter (Selenium send_keys Enter ổn định hơn click nút search ảo)
                        search_box.send_keys(Keys.ENTER)
                        
                        # Ghi nhận ngay lập tức, không chờ reload trang quá lâu
                        save_history(book_id)
                        processed_ids.add(book_id)
                        
                        # Cộng vào biến toàn cục thay vì biến local
                        total_success_count += 1
                        
                        current_qsize = link_queue.qsize()
                        synchronized_print(f"   [>> OK #{total_success_count}] {book_id} | Còn: {current_qsize}")
                        
                        # Giảm thời gian nghỉ sau khi nhúng thành công xuống mức tối thiểu
                        time.sleep(0.1) 
                        break

                    except Exception as e:
                        if "Attention" in str(e):
                            synchronized_print("\n[!!!] Lỗi 1015. Ngủ 45s...")
                            time.sleep(45)
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

# --- THREAD 2: QUÉT LINK (PRODUCER) - ĐÃ TỐI ƯU ---
def scanner_thread(custom_url, source_type, processed_ids, loop_range=None, batch_mode=False):
    global global_scanner_driver
    
    # Đặt vị trí bên trái
    global_scanner_driver = get_active_driver(global_scanner_driver, position=(0, 0))
    driver = global_scanner_driver
    
    urls_to_run = []
    if batch_mode:
        urls_to_run = read_batch_file()
        if not urls_to_run:
            synchronized_print(f"[Scanner] File {BATCH_FILE} rỗng!")
            stop_event.set()
            return
        synchronized_print(f"[Scanner] Load {len(urls_to_run)} link từ Batch.")
    else:
        urls_to_run = [custom_url]

    try:
        for url_index, current_target_url in enumerate(urls_to_run):
            if stop_event.is_set(): break
            
            synchronized_print(f"\n[Scanner] >>> SCAN LINK #{url_index + 1}: {current_target_url}")

            # --- SETUP URL TEMPLATE ---
            url_template = None
            current_page = 1
            single_page_mode = False 
            
            if source_type == "fanqie":
                match = re.search(r'page_(\d+)', current_target_url)
                if match:
                    current_page = int(match.group(1)) 
                    url_template = current_target_url.replace(f"page_{current_page}", "page_{}")
                else: 
                     if "?" in current_target_url: single_page_mode = True 
                     else: single_page_mode = True
            
            elif source_type == "jjwxc":
                match = re.search(r'page=(\d+)', current_target_url)
                if match:
                    current_page = int(match.group(1))
                    url_template = current_target_url.replace(f"page={current_page}", "page={}")
                else: single_page_mode = True
            elif source_type == "qimao":
                match = re.search(r'-(\d+)/?$', current_target_url)
                if match:
                    current_page = int(match.group(1))
                    prefix = current_target_url[:match.start(1)]
                    suffix = current_target_url[match.end(1):]
                    url_template = f"{prefix}{{}}{suffix}"
                else: single_page_mode = True
            elif source_type == "ciweimao":
                match = re.search(r'/(\d+)/?$', current_target_url)
                if match:
                    current_page = int(match.group(1))
                    url_template = current_target_url[:match.start(1)] + "/{}" + current_target_url[match.end(1):]
                else: single_page_mode = True
            elif source_type == "sfacg":
                match = re.search(r'PageIndex=(\d+)', current_target_url, re.IGNORECASE)
                if match:
                    current_page = int(match.group(1))
                    url_template = re.sub(r'PageIndex=\d+', 'PageIndex={}', current_target_url, flags=re.IGNORECASE)
                else: single_page_mode = True
            elif source_type == "69shu":
                single_page_mode = True
            elif source_type == "quanben5":
                match = re.search(r'_(\d+)\.html', current_target_url)
                if match:
                    current_page = int(match.group(1))
                    url_template = current_target_url.replace(f"_{current_page}.html", "_{}.html")
                elif current_target_url.endswith(".html"):
                    current_page = 1
                    url_template = current_target_url[:-5] + "_{}.html"
                else:
                    single_page_mode = True

            if loop_range: current_page = loop_range[0]
            
            pages_scanned_for_this_url = 0
            local_queue_cache = [] 

            # --- VÒNG LẶP QUÉT TRANG ---
            while not stop_event.is_set():
                if pages_scanned_for_this_url >= 1000:
                    synchronized_print(f"[Scanner] Đã quét đủ 1000 trang. Next link.")
                    break

                if single_page_mode: target_url = current_target_url
                else: 
                    if source_type == "quanben5" and current_page == 1:
                        if "_{}" in url_template: target_url = url_template.replace("_{}.html", ".html")
                        else: target_url = current_target_url
                    else:
                        try: target_url = url_template.format(current_page)
                        except: target_url = current_target_url

                # Hiển thị rõ ràng đang quét trang nào và hàng đợi hiện tại
                current_q_size = link_queue.qsize()
                synchronized_print(f"\n[Scanner] --------------------------------------------------")
                synchronized_print(f"[Scanner] 📄 Đang quét TRANG {current_page} | Hàng đợi đang chờ: {current_q_size}")
                
                try:
                    driver.get(target_url)
                    
                    # --- TỐI ƯU SCROLL ---
                    if source_type in ["fanqie", "qimao", "ciweimao", "sfacg"]:
                        # Cuộn 1 phát xuống cuối luôn hoặc cuộn ít lần
                        for _ in range(SCROLL_TIMES):
                            if stop_event.is_set(): break
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(SCROLL_DELAY) # Sleep cực ngắn

                    if stop_event.is_set(): break

                    # Tìm element (Logic cũ nhưng chạy nhanh hơn do tắt ảnh)
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
                        
                        is_valid = False
                        # Validate nhanh
                        if source_type == "fanqie" and "fanqienovel.com/page/" in raw_href: is_valid = True
                        elif source_type == "jjwxc" and "novelid=" in raw_href and "chapterid=" not in raw_href: is_valid = True
                        elif source_type == "qimao" and "/shuku/" in raw_href and re.search(r'/shuku/\d+/?$', raw_href): is_valid = True
                        elif source_type == "ciweimao" and "/book/" in raw_href and re.search(r'/book/\d+/?$', raw_href): is_valid = True
                        elif source_type == "sfacg" and "/Novel/" in raw_href and re.search(r'/Novel/\d+/?$', raw_href): is_valid = True
                        elif source_type == "69shu" and (".htm" in raw_href): is_valid = True
                        elif source_type == "quanben5" and "/n/" in raw_href: is_valid = True
                        
                        if is_valid:
                            book_id = get_book_id(raw_href)
                            # Kiểm tra Cache cục bộ trước để đỡ tốn time check file
                            if book_id and book_id not in processed_ids and book_id not in local_queue_cache:
                                book_text = ""
                                try:
                                    if source_type == "jjwxc": book_text = elem.find_element(By.XPATH, "./ancestor::tr").text
                                    else: book_text = elem.text 
                                    if not book_text: book_text = elem.find_element(By.XPATH, "./..").text
                                except: pass
                                
                                if check_is_recent(book_text):
                                    link_queue.put((book_id, raw_href))
                                    local_queue_cache.append(book_id)
                                    found_new_on_page = True
                                    # Hiển thị dấu cộng rõ ràng
                                    synchronized_print(f"   [+] Phát hiện truyện mới: {book_id}")
                                
                                elif source_type == "fanqie" and "sort=newest" in target_url:
                                    # Gặp truyện cũ thì dừng luôn link này cho nhanh
                                    pages_scanned_for_this_url = 2000 
                                    found_new_on_page = False
                                    break

                    if not found_new_on_page and not loop_range and pages_scanned_for_this_url < 2000:
                        if single_page_mode: break
                    
                    if single_page_mode: break
                    
                    current_page += 1
                    pages_scanned_for_this_url += 1
                    
                    if loop_range:
                        if current_page > loop_range[1]: current_page = loop_range[0]

                except Exception as e:
                    synchronized_print(f"[Scanner] Err: {e}")
                    time.sleep(1)
        
        synchronized_print("[Scanner] DONE ALL LINKS.")

    except Exception as e:
        synchronized_print(f"[Scanner] Crash: {e}")
    finally:
        stop_event.set() 
        synchronized_print("[Scanner] Stopped.")

def run_concurrent_mode(custom_url, source_type, loop_range=None, is_fast_mode=False, batch_mode=False):
    processed_ids = load_history()
    print(f"\n[*] CHẾ ĐỘ TĂNG TỐC (IMAGES ON + JS INJECTION)")
    
    stop_event.clear()
    with link_queue.mutex:
        link_queue.queue.clear()
    
    t_embedder = threading.Thread(target=embedder_thread, args=(processed_ids, is_fast_mode))
    t_scanner = threading.Thread(target=scanner_thread, args=(custom_url, source_type, processed_ids, loop_range, batch_mode))
    
    t_embedder.start()
    time.sleep(1) 
    t_scanner.start()
    
    while t_scanner.is_alive() or t_embedder.is_alive():
        if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
            print("\n[!!!] NHẬN LỆNH DỪNG...")
            stop_event.set()
            break
        time.sleep(0.5)
        
        if stop_event.is_set() or (not t_scanner.is_alive() and link_queue.empty()):
            stop_event.set() 
            break

    print("[Main] Đang dừng luồng...")
    t_scanner.join()
    t_embedder.join()
    print("[Main] Xong.")

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
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(800, 0))
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
    ensure_dirs_and_files()
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n=== ⚡ AUTO NHÚNG SIÊU TỐC (IMAGES ON) ⚡ ===")
        print("--------------------------------------------------")
        print(" 1. 🍅 Fanqie (Cà Chua) [FAST]")
        print(" 2. 🌿 Jjwxc (Tấn Giang)")
        print(" 3. 🐱 Qimao (Thất Miêu)")
        print(" 4. 🦔 Ciweimao (Thất Vĩ Miêu)")
        print(" 5. 🍍 SFACG (B菠萝包)")
        print(" 6. 📖 69shu (Lục Cửu)")
        print(" 7. 📚 Quanben5 (Toàn Bản 5)")
        print(" 8. ♾️  Loop Fanqie (700-3000)")
        print("--------------------------------------------------")
        print(" 11.📁 Batch Fanqie (Đọc từ file)")
        print("--------------------------------------------------")
        print(" 9. 🖥️  Mở 2 Trình duyệt treo máy")
        print(" 10.📊 Xem thống kê ID")
        print(" 0. ❌ Thoát")
        print("==================================================")
        
        choice = input("👉 Chọn: ").strip()
        
        url = None; stype = None; loop_cfg = None; fast = True; batch = False
        
        if choice == '1':
            url = input("Link Fanqie: ").strip()
            stype = "fanqie"
        elif choice == '2':
            url = input("Link Jjwxc: ").strip()
            stype = "jjwxc"
        elif choice == '3':
            url = input("Link Qimao: ").strip()
            stype = "qimao"
        elif choice == '4':
            url = input("Link Ciweimao: ").strip()
            stype = "ciweimao"
        elif choice == '5':
            url = input("Link SFACG: ").strip()
            stype = "sfacg"
        elif choice == '6':
            print("Link 69shu (VD: https://www.69shuba.com/novels/class/0.htm)")
            url = input("Link: ").strip()
            stype = "69shu"
        elif choice == '7':
            url = input("Link Quanben5: ").strip()
            stype = "quanben5"
        elif choice == '8':
            url = "https://fanqienovel.com/library/audience1-cat2-19-stat1-count0/page_700?sort=newest"
            stype = "fanqie"
            loop_cfg = (700, 3000)
        elif choice == '11':
            url = "BATCH"; stype = "fanqie"; batch = True
        elif choice == '9':
            open_both_browsers_only()
        elif choice == '10':
            current_ids = load_history()
            print(f"\n[INFO] Đã nhúng tổng cộng: {len(current_ids)} truyện.")
            input("Enter về menu...")
        elif choice == '0':
            close_all_drivers()
            break
            
        if url and stype:
            run_concurrent_mode(url, stype, loop_range=loop_cfg, is_fast_mode=fast, batch_mode=batch)
            input("\nEnter để tiếp tục...")

if __name__ == "__main__":
    main()