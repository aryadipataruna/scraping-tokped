from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import urllib.parse
import mysql.connector 

# =====================================================================
# PERSIAPAN DATABASE MYSQL
# =====================================================================
print("[INFO] Menghubungkan ke database...")
try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",      # Sesuaikan jika user MySQL Anda berbeda
        password="",      # Sesuaikan jika MySQL Anda pakai password
        database="scraping"
    )
    cursor = db.cursor()
    print("   [V] Berhasil terhubung ke MySQL!")
except Exception as e:
    print(f"   [X] Gagal terhubung ke MySQL: {e}")
    exit() 

# =====================================================================
# INISIASI SELENIUM & INPUT USER
# =====================================================================
barang = input("\nMasukkan barang yang dicari: ")
barang_encoded = urllib.parse.quote(barang)

options = webdriver.ChromeOptions()
options.page_load_strategy = 'eager' 

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(45) 
wait = WebDriverWait(driver, 15)

try:
    url = f"https://www.tokopedia.com/search?fcity=253&q={barang_encoded}"
    
    print(f"\n[INFO] Membuka halaman pencarian untuk: {barang}...")
    try:
        driver.get(url)
    except TimeoutException:
        print("   [!] Loading halaman utama lambat, memaksa lanjut...")
        driver.execute_script("window.stop();")

    driver.maximize_window()
    driver.execute_script("document.body.style.zoom = '75%'")
    time.sleep(3)
    
    # =====================================================================
    # (OPSIONAL) FILTER LOKASI KABUPATEN BANTUL
    # =====================================================================
    # print("[INFO] Menerapkan filter lokasi Kabupaten Bantul...")
    # try:
    #     lihat_selengkapnya = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='lnkSRPSeeAllLocFilter']")))
    #     driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", lihat_selengkapnya)
    #     time.sleep(1)
    #     driver.execute_script("arguments[0].click();", lihat_selengkapnya)
        
    #     search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='Cari lokasi']")))
    #     search_box.clear()
    #     search_box.send_keys("bantul")
    #     time.sleep(2) 
        
    #     checkbox_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='Kab. Bantul']")))
    #     if not checkbox_input.is_selected():
    #         driver.execute_script("arguments[0].click();", checkbox_input)
    #     time.sleep(2) 
        
    #     btn_terapkan = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Terapkan') or @data-testid='btnSRPApplySeeAllFilter']")))
    #     driver.execute_script("arguments[0].scrollIntoView(true);", btn_terapkan)
    #     time.sleep(0.5)
    #     driver.execute_script("arguments[0].click();", btn_terapkan)
        
    #     print("   [V] Filter lokasi berhasil diterapkan.")
    #     time.sleep(4)
    # except Exception as e:
    #     print(f"   [X] Gagal saat proses filter lokasi, melanjutkan tanpa filter...")

    # =====================================================================
    # TAHAP 1: KUMPULKAN URL DAN NAMA PRODUK
    # =====================================================================
    print("\n[INFO] Mulai mengumpulkan link produk...")
    daftar_produk = [] 
    
    try:
        main_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='divSRPContentProducts']")))
        print("   Melakukan scrolling bertahap...")
        
        for i in range(15):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1.2) 
            
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Cari kartu produk
        product_cards = main_container.find_elements(By.CSS_SELECTOR, "div.css-5wh65g")
        if not product_cards: product_cards = main_container.find_elements(By.CSS_SELECTOR, ".pcv3__container")
        if not product_cards: product_cards = main_container.find_elements(By.CSS_SELECTOR, "[data-testid='master-product-card']")
            
        print(f"   Ditemukan {len(product_cards)} kartu produk. Mengekstrak link...")
        
        for card in product_cards:
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", card)
            except: pass
            
            try: nama_produk = card.find_element(By.CSS_SELECTOR, "[class*='SzILjt4fxHUFNVT48ZPhHA']").text
            except:
                try: nama_produk = card.find_element(By.CSS_SELECTOR, ".prd_link-product-name").text
                except: nama_produk = "Nama tidak ditemukan"

            try: 
                link_mentah = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                # Memotong URL pada tanda '?' untuk membuang kode pelacakan dinamis Tokopedia
                link_produk = link_mentah.split('?')[0] if link_mentah else None
            except: link_produk = None

            if link_produk:
                daftar_produk.append({"nama": nama_produk, "link": link_produk})
                
    except Exception as e:
        print(f"   [X] Gagal mengambil data awal: {e}")

    # --- Hapus duplikat link ---
    seen_links = set()
    unique_daftar_produk = []
    for item in daftar_produk:
        if item['link'] not in seen_links:
            seen_links.add(item['link'])
            unique_daftar_produk.append(item)

    print(f"   Total link unik yang akan diproses: {len(unique_daftar_produk)}")

    # =====================================================================
    # TAHAP 2: BUKA HALAMAN DETAIL & SIMPAN KE DATABASE
    # =====================================================================
    print(f"\n[INFO] Mulai memproses halaman detail produk (PDP) dan menyimpan ke MySQL...")
    
    for index, produk in enumerate(unique_daftar_produk, 1):
        try:
            print(f"\n[{index}/{len(unique_daftar_produk)}] Mengunjungi: {produk['nama'][:50]}...")

            # Mengecek apakah link produk ini sudah pernah disimpan sebelumnya
            cek_sql = "SELECT id FROM produk_tokopedia WHERE link = %s or nama_produk = %s"
            cursor.execute(cek_sql, (produk['link'], produk['nama']))
            hasil_cek = cursor.fetchone()
            
            if hasil_cek:
                print("   [-] Produk sudah ada di database. Melewati (Skip)...")
                continue 
            
            # akses halaman detail produk
            try:
                driver.get(produk['link'])
            except TimeoutException:
                print("   [!] Loading halaman terlalu lama, stop paksa & lanjut ekstrak...")
                driver.execute_script("window.stop();") 
            except Exception as e:
                print(f"   [!] Gagal total membuka link. Error: {e}")
                continue 
            
            driver.execute_script("document.body.style.zoom = '65%'")
            
            try: wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[role='tabpanel'], [data-testid='lblPDPDetailProductName']")))
            except: pass 
                
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(1) 
            
            try:
                img_element = driver.find_element(By.CSS_SELECTOR, "img[class='css-1logqad active']")
                gambar = img_element.get_attribute("src")
            except:
                try:
                    img_element = driver.find_element(By.CSS_SELECTOR, "[data-testid='imgLeg-c'] img")
                    gambar = img_element.get_attribute("src")
                except:
                    gambar = "Gambar tidak ditemukan"

            try: harga_utama = driver.find_element(By.CSS_SELECTOR, "[data-testid='lblPDPDetailProductPrice']").text
            except: harga_utama = "Harga tidak ditemukan"

            try: harga_asli = driver.find_element(By.CSS_SELECTOR, "[data-testid='lblPDPDetailOriginalPrice']").text
            except: harga_asli = "-"

            try: diskon_persen = driver.find_element(By.CSS_SELECTOR, "span.css-1c4ggdd").text
            except: diskon_persen = "-"

            try: terjual_teks = driver.find_element(By.CSS_SELECTOR, "[data-testid='lblPDPDetailProductSoldCounter']").text
            except: terjual_teks = "0 Terjual"

            try: rating_teks = driver.find_element(By.CSS_SELECTOR, "[data-testid='lblPDPDetailProductRatingNumber']").text
            except: rating_teks = "Belum ada rating"

            try:
                ul_info = driver.find_element(By.CSS_SELECTOR, "ul[data-testid='lblPDPInfoProduk'], ul.css-yxla8g")
                li_elements = ul_info.find_elements(By.TAG_NAME, "li")
                info_detail = [li.text.replace('\n', ': ') for li in li_elements]
                spesifikasi_teks = ' | '.join(info_detail)
            except:
                spesifikasi_teks = "Info spesifikasi tidak ditemukan"
                
            try:
                btn_more = driver.find_elements(By.CSS_SELECTOR, "[data-testid='btnPDPSeeMore'], button.css-1nv6gtb")
                if len(btn_more) > 0:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn_more[0])
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn_more[0])
                    time.sleep(1) 
            except: pass
                
            try:
                div_desc = driver.find_element(By.CSS_SELECTOR, "div.css-ti3w3y, [data-testid='lblPDPDescriptionProduk']")
                deskripsi_teks = div_desc.text
            except:
                deskripsi_teks = "Deskripsi tidak ditemukan"

            # --- MENGIRIM DATA KE MYSQL ---
            sql = """INSERT INTO produk_tokopedia 
                     (kategori, nama_produk, harga_utama, harga_asli, diskon, terjual, rating, spesifikasi, deskripsi, link, gambar) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            val = (
                barang,          # Kategori berdasarkan input user
                produk['nama'], 
                harga_utama, 
                harga_asli, 
                diskon_persen, 
                terjual_teks, 
                rating_teks, 
                spesifikasi_teks, 
                deskripsi_teks, 
                produk['link'],
                gambar
            )
            
            try:
                cursor.execute(sql, val)
                db.commit() 
                print(f"   [V] Berhasil disimpan ke Database! (Kategori: {barang})")
            except Exception as err:
                print(f"   [X] Gagal menyimpan ke DB: {err}")
                db.rollback() 
            
            time.sleep(1.5) # Jeda per produk agar tidak terdeteksi DDOS
            
        except Exception as e:
            print(f"   [X] Gagal mengekstrak detail produk ke-{index}: {e}")
            try: driver.refresh()
            except: pass

finally:
    print("\n[INFO] Proses Selesai. Menutup koneksi dan browser dalam 5 detik...")
    try:
        cursor.close()
        db.close()
    except: pass
    
    time.sleep(5) 
    driver.quit()