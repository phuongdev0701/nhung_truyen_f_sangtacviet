import time
import os # Thư viện thao tác file, xóa màn hình
import re # Thư viện xử lý chuỗi (Regex) để tách số trang
import msvcrt # Thư viện hỗ trợ bắt phím trên Windows
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Cấu hình Mặc định
FANQIE_DEFAULT_TEMPLATE = "https://fanqienovel.com/library/audience1-cat2-19-stat1-count0/page_{}?sort=newest"
SANGTACVIET_URL = "https://sangtacviet.app/"
SCROLL_TIMES = 3  
HISTORY_FILE = "da_lam_xong.txt"

# --- CẤU HÌNH TÀI KHOẢN (NGƯỜI DÙNG TỰ ĐIỀN) ---
# Lưu ý: Không điền mật khẩu thật vào đây khi up lên GitHub
STV_USERNAME = "YOUR_USERNAME_HERE" 
STV_PASSWORD = "YOUR_PASSWORD_HERE"

def setup_driver():
    """Khởi tạo trình duyệt Chrome"""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("detach", True)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_history(link):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

def login_to_stv(driver, wait):
    print("--- Đang truy cập Sangtacviet ---")
    driver.get(SANGTACVIET_URL)
    
    try:
        try:
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Đăng nhập')] | //button[contains(text(), 'Đăng nhập')]")))
            login_btn.click()
            print("-> Đã mở form đăng nhập")

            username_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username'], input[placeholder*='Tài khoản'], input[type='text']")))
            username_field.clear()
            username_field.send_keys(STV_USERNAME)

            password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password'], input[placeholder*='Mật khẩu'], input[type='password']")
            password_field.clear()
            password_field.send_keys(STV_PASSWORD)

            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], div.modal-footer button")
            if not submit_btn:
                 submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Đăng nhập')]")
            
            submit_btn.click()
            print(f"-> Đã điền thông tin cho user: {STV_USERNAME}")
            time.sleep(3)
        except:
            print("-> Có vẻ bạn ĐÃ đăng nhập rồi hoặc không tìm thấy nút đăng nhập.")
            
    except Exception as e:
        print(f"!! Lỗi khi thao tác login: {e}")

def run_automation(driver, wait, custom_url=None):
    """Hàm chính thực hiện quét và nhúng truyện."""
    processed_links = load_history()
    print(f"\n[*] Đã tải lịch sử: {len(processed_links)} truyện đã làm.")

    url_template = None
    current_page = 1
    single_page_mode = False 

    # --- XỬ LÝ LINK ---
    if custom_url:
        match = re.search(r'page_(\d+)', custom_url)
        if match:
            current_page = int(match.group(1)) 
            url_template = custom_url.replace(f"page_{current_page}", "page_{}")
            print(f"[*] Đã nhận diện link nhiều trang. Bắt đầu từ trang {current_page}...")
        else:
            single_page_mode = True
            print("[*] Link này không có số trang (page_X). Tool sẽ chỉ quét 1 lần trang này.")
    else:
        url_template = FANQIE_DEFAULT_TEMPLATE
        current_page = 1

    # --- VÒNG LẶP CHÍNH ---
    while True:
        if single_page_mode:
            target_url = custom_url
        else:
            target_url = url_template.format(current_page)

        print(f"\n==================================================")
        if single_page_mode:
             print(f"[*] ĐANG XỬ LÝ LINK TÙY CHỈNH (1 TRANG)")
        else:
             print(f"[*] ĐANG XỬ LÝ TRANG SỐ: {current_page}")
        print(f"[*] Link: {target_url}")
        print(f"==================================================")
        
        driver.get(target_url)
        time.sleep(3)

        print(f"[*] Đang lăn chuột {SCROLL_TIMES} lần...")
        for i in range(SCROLL_TIMES):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        print("[*] Đang quét danh sách truyện...")
        story_elements = driver.find_elements(By.CSS_SELECTOR, "a[href^='/page/']")
        
        story_links = []
        for elem in story_elements:
            href = elem.get_attribute('href')
            if href and "fanqienovel.com/page/" in href:
                if href not in story_links: 
                    story_links.append(href)

        if not story_links:
            print(f"[!] Không tìm thấy truyện nào. Có thể link sai hoặc hết truyện.")
            print("-> Dừng Auto.")
            break

        todo_links = [link for link in story_links if link not in processed_links]
        print(f"[+] Tìm thấy {len(story_links)} truyện. Cần làm mới: {len(todo_links)}.")
        
        if len(todo_links) == 0:
            if single_page_mode:
                print("-> Đã kiểm tra xong link tùy chỉnh. Dừng.")
                break
            else:
                print(f"-> Trang {current_page} đã làm hết. Chuyển sang trang tiếp theo...")
                current_page += 1
                continue

        print("=> Nhấn phím 'q' để DỪNG và quay về MENU.")
        original_window = driver.current_window_handle
        stop_requested = False

        for index, link in enumerate(todo_links):
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key.lower() == b'q':
                    print("\n[!!!] Đã nhận lệnh dừng. Quay về Menu.")
                    stop_requested = True
                    break

            print(f"\n--- Trang {current_page if not single_page_mode else 'Custom'} | Truyện {index + 1}/{len(todo_links)} ---")
            
            driver.switch_to.new_window('tab')
            driver.get(SANGTACVIET_URL)
            
            try:
                search_box = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                search_box.clear()
                search_box.send_keys(link)
                time.sleep(0.5)
                search_box.send_keys(Keys.ENTER)
                print("-> Đã tìm kiếm...")
                time.sleep(3) 
                
                save_history(link)
                processed_links.add(link)
                print("-> Xong.")

            except Exception as e:
                print(f"!! Lỗi: {e}")
            
            driver.close()
            driver.switch_to.window(original_window)
            time.sleep(1)
        
        if stop_requested:
            break
            
        print(f"\n[DONE] Hoàn thành đợt quét này.")
        
        if single_page_mode:
            print("-> Kết thúc chế độ chạy link đơn.")
            break 
        else:
            current_page += 1
            time.sleep(2)

def main():
    driver = None
    wait = None

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("\n================ MENU TOOL ================")
        print("1. Mở trang Sangtacviet (Đăng nhập/Check)")
        print("2. Chạy Auto (Link Mặc Định trong code)")
        print("3. Chạy Auto với Link Fanqie khác (Nhập tay)")
        print("4. Thoát tool")
        print("===========================================")
        
        choice = input("Nhập lựa chọn (1-4): ").strip()
        
        if choice in ['1', '2', '3']:
            if driver is None:
                print("\n[*] Đang khởi động trình duyệt...")
                driver = setup_driver()
                wait = WebDriverWait(driver, 15)

            if choice == '1':
                login_to_stv(driver, wait)
                input("\n-> Nhấn Enter để quay lại Menu...")
            
            elif choice == '2':
                run_automation(driver, wait, custom_url=None)
                input("\n-> Đợt chạy kết thúc. Nhấn Enter để quay lại Menu...")
            
            elif choice == '3':
                print("\n--- NHẬP LINK FANQIE ---")
                print("Gợi ý: Nếu muốn chạy nhiều trang, hãy nhập link của trang 1.")
                print("Ví dụ: https://fanqienovel.com/.../page_1?sort=newest")
                user_link = input("Dán link vào đây: ").strip()
                
                if user_link:
                    run_automation(driver, wait, custom_url=user_link)
                else:
                    print("Link trống! Đã hủy.")
                
                input("\n-> Đợt chạy kết thúc. Nhấn Enter để quay lại Menu...")
        
        elif choice == '4':
            print("Tạm biệt!")
            if driver:
                driver.quit()
            break
        else:
            print("Lựa chọn không hợp lệ.")
            time.sleep(1)

if __name__ == "__main__":
    main()