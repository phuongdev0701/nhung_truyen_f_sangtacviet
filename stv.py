import time
import os 
import re 
import msvcrt 
import threading
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
    position: tuple (x, y) để đặt vị trí cửa sổ
    """
    options = webdriver.ChromeOptions()
    # options.add_argument("--start-maximized") 
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
    """
    Kiểm tra driver còn sống không, nếu không thì tạo mới.
    """
    try:
        # Thử truy cập thuộc tính title để xem browser còn sống không
        _ = driver_ref.title
        return driver_ref
    except:
        # Nếu lỗi (người dùng tắt tay hoặc crash), tạo mới
        return setup_driver(position)

def close_all_drivers():
    """Đóng toàn bộ driver khi thoát chương trình"""
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
    
    # Định dạng ngắn MM-DD
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
def embedder_thread(processed_ids):
    """Luồng chuyên nhúng truyện vào Sangtacviet"""
    global global_embedder_driver
    
    # Lấy hoặc tạo driver (bên phải màn hình)
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(960, 0))
    driver = global_embedder_driver
    
    try:
        wait = WebDriverWait(driver, 10)
        
        # Chỉ vào STV nếu chưa ở đó (để tránh reload không cần thiết)
        if "sangtacviet.app" not in driver.current_url:
            synchronized_print("[Embedder] Đang vào Sangtacviet...")
            try:
                driver.get(SANGTACVIET_URL)
                # --- LOGIN ---
                try:
                    login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
                    login_btn.click()
                    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(STV_USERNAME)
                    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(STV_PASSWORD)
                    submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
                    if not submit: submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
                    submit.click()
                    time.sleep(2)
                except: pass # Đã đăng nhập rồi thì thôi
            except Exception as e:
                synchronized_print(f"[Embedder] Lỗi truy cập STV: {e}")

        # --- VÒNG LẶP NHÚNG ---
        # Chỉ chạy khi KHÔNG có lệnh dừng
        while not stop_event.is_set():
            try:
                # Lấy link từ hàng đợi (chờ tối đa 1s để check lại stop_event)
                task = link_queue.get(timeout=1)
                
                # NẾU CÓ LỆNH DỪNG -> THOÁT NGAY
                if stop_event.is_set():
                    break

                book_id, link = task
                
                if book_id in processed_ids:
                    link_queue.task_done()
                    continue

                synchronized_print(f"-> [Nhúng] Đang xử lý ID: {book_id}")
                
                success = False
                for attempt in range(2): # Thử 2 lần
                    if stop_event.is_set(): break 

                    try:
                        driver.set_page_load_timeout(10)
                        
                        search_box = None
                        try:
                            search_box = driver.find_element(By.TAG_NAME, "input")
                        except:
                            driver.get(SANGTACVIET_URL)
                            search_box = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))

                        search_box.clear()
                        try:
                            search_box.send_keys(Keys.CONTROL + "a")
                            search_box.send_keys(Keys.DELETE)
                        except: pass
                        
                        search_box.send_keys(link)
                        search_box.send_keys(Keys.ENTER)
                        
                        save_history(book_id)
                        processed_ids.add(book_id)
                        synchronized_print(f"   [OK] ID {book_id} xong.")
                        success = True
                        break
                    
                    except Exception as e:
                        try: 
                            # Nếu lỗi, thử quay về trang chủ, không tắt driver
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
        # KHÔNG ĐÓNG DRIVER TẠI ĐÂY
        synchronized_print("[Embedder] Đã dừng chờ lệnh mới.")

# --- THREAD 2: QUÉT LINK (PRODUCER) ---
def scanner_thread(custom_url, source_type, processed_ids):
    """Luồng chuyên đi quét link từ các nguồn"""
    global global_scanner_driver
    
    # Lấy hoặc tạo driver (bên trái màn hình)
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
        else: # Fanqie
            match = re.search(r'page_(\d+)', custom_url)
            if match:
                current_page = int(match.group(1)) 
                url_template = custom_url.replace(f"page_{current_page}", "page_{}")
            else: single_page_mode = True

        local_queue_cache = [] 

        while not stop_event.is_set():
            if single_page_mode: target_url = custom_url
            else: target_url = url_template.format(current_page)

            synchronized_print(f"\n[Scanner] Đang quét trang {current_page}...")
            
            try:
                driver.set_page_load_timeout(30)
                driver.get(target_url)
                time.sleep(1.5)
                
                # Cuộn trang
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
                if current_page > 1000: current_page = 1

            except Exception as e:
                synchronized_print(f"[Scanner] Lỗi quét: {e}")
                time.sleep(3)

    except Exception as e:
        synchronized_print(f"[Scanner] Crash: {e}")
    finally:
        # KHÔNG ĐÓNG DRIVER
        stop_event.set() 
        synchronized_print("[Scanner] Đã dừng chờ lệnh mới.")

def run_concurrent_mode(custom_url, source_type):
    processed_ids = load_history()
    print(f"\n[*] Đang khởi động chế độ SONG SONG (2 Trình duyệt)...")
    print(f"[*] Nhấn phím 'q' để DỪNG (Trình duyệt sẽ giữ nguyên).")
    print(f"[*] LƯU Ý: Bấm vào cửa sổ dòng lệnh (CMD) trước khi ấn 'q'.")
    
    stop_event.clear()
    with link_queue.mutex:
        link_queue.queue.clear()
    
    t_embedder = threading.Thread(target=embedder_thread, args=(processed_ids,))
    t_scanner = threading.Thread(target=scanner_thread, args=(custom_url, source_type, processed_ids))
    
    t_embedder.start()
    time.sleep(2) 
    t_scanner.start()
    
    while t_scanner.is_alive() or t_embedder.is_alive():
        if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
            print("\n[!!!] NHẬN LỆNH DỪNG TỪ BÀN PHÍM. ĐANG THOÁT NGAY...")
            stop_event.set()
            time.sleep(1)
            break
        time.sleep(0.5)
        
        if stop_event.is_set() or (not t_scanner.is_alive() and link_queue.empty()):
            stop_event.set() 
            break

    print("[Main] Đang đợi các luồng về trạng thái nghỉ...")
    t_scanner.join()
    t_embedder.join()
    print("[Main] Đã dừng. (Chrome vẫn mở để bạn dùng tiếp).")

def open_stv_only():
    """Mở STV bằng driver toàn cục để tái sử dụng"""
    global global_embedder_driver
    print("[*] Đang mở trình duyệt Embedder (Phải)...")
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(960, 0))
    driver = global_embedder_driver
    
    print("--- Đang truy cập Sangtacviet ---")
    try:
        driver.get(SANGTACVIET_URL)
        # Login logic (giống ở trên)...
        try:
            wait = WebDriverWait(driver, 5)
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
            login_btn.click()
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username']"))).send_keys(STV_USERNAME)
            driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(STV_PASSWORD)
            submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
            if not submit: submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
            submit.click()
            print(f"-> Đã gửi đăng nhập: {STV_USERNAME}")
        except:
            print("-> Đã sẵn sàng.")
            
        print("\n-> Trình duyệt đã mở. Nhấn Enter để quay về Menu.")
        input()
    except Exception as e:
        print(f"Lỗi: {e}")

def open_both_browsers_only():
    """Mở cả 2 trình duyệt Scanner và Embedder rồi treo đó"""
    global global_scanner_driver, global_embedder_driver
    
    print("\n[*] Đang khởi động/kiểm tra 2 trình duyệt...")
    
    # 1. Scanner Driver
    print("   -> Scanner Driver (Trái)...")
    global_scanner_driver = get_active_driver(global_scanner_driver, position=(0, 0))
    try:
        # Mở trang trắng
        if "data:," in global_scanner_driver.current_url:
             global_scanner_driver.get("about:blank")
    except: pass

    # 2. Embedder Driver
    print("   -> Embedder Driver (Phải)...")
    global_embedder_driver = get_active_driver(global_embedder_driver, position=(960, 0))
    
    # Login STV cho Embedder
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
        print("   1. 🍅 Chạy nguồn Fanqie (Cà Chua)")
        print("   2. 🌿 Chạy nguồn Jjwxc (Tấn Giang)")
        print("   3. 🐱 Chạy nguồn Qimao (Thất Miêu)")
        print("   4. 🦔 Chạy nguồn Ciweimao (Thất Vĩ Miêu)")
        print("   5. 🍍 Chạy nguồn SFACG (B菠萝包)")
        print("-----------------------------------------------------------------------")
        print("   6. 🖥️  Mở 2 Trình duyệt (Scanner & Embedder) để treo")
        print("   7. 🌐 Mở riêng Sangtacviet (Đăng nhập)")
        print("   8. ❌ Thoát (Đóng tất cả)")
        print("=======================================================================")
        
        choice = input("👉 Chọn chức năng (1-8): ").strip()
        
        url = None
        stype = None
        
        if choice == '1':
            url = input("\n🔗 Nhập Link Fanqie: ").strip()
            stype = "fanqie"
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
            open_both_browsers_only()
        elif choice == '7':
            open_stv_only()
        elif choice == '8':
            close_all_drivers()
            print("👋 Tạm biệt!")
            break
            
        if url and stype:
            run_concurrent_mode(url, stype)
            input("\n-> Enter về Menu...")

if __name__ == "__main__":
    main()