# ========== [IMPORT LIBRARY] ==========
import os
import time
import re
import traceback
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from deep_translator import GoogleTranslator
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ========== [FUNGSI TAMBAHAN] ==========

# Fungsi untuk menghitung berapa banyak mention (@username) dalam komentar
def count_mentions(comment):
    return len(re.findall(r"@\w+", comment))

# Fungsi untuk menerjemahkan komentar ke bahasa Inggris
def translate_comment(comment):
    if not comment:
        return "No Comment"
    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(comment)
        print(f"Translation done: {translated_text}")
        return translated_text
    except Exception as e:
        print(f"Translation error on: {comment} ({e})")
        return comment  # Kalau gagal, kembalikan teks asli

# ========== [LOAD ENV & LOGIN INSTAGRAM] ==========

# Load username dan password dari file .env
load_dotenv()
username = os.getenv('IG_USERNAME')
password = os.getenv('IG_PASSWORD')

# Inisialisasi ChromeDriver
driver = webdriver.Chrome()

# Akses halaman login Instagram
driver.get("https://www.instagram.com/accounts/login/")
time.sleep(3)

# Login ke Instagram
driver.find_element(By.NAME, "username").send_keys(username)
driver.find_element(By.NAME, "password").send_keys(password + Keys.RETURN)
time.sleep(6)  # Tunggu proses login selesai

# ========== [AKSES HASHTAG & KOLEKSI LINK POSTINGAN] ==========

hashtag = "prabowo"
driver.get(f"https://www.instagram.com/explore/tags/{hashtag}/")
time.sleep(7)

post_links = set()
for _ in range(1):  # Tambah range untuk scroll lebih banyak
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(6)
    posts = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
    for post in posts:
        post_links.add(post.get_attribute("href"))

print(f"✅ Collected {len(post_links)} post links.")

# ========== [SCRAPING KOMENTAR PER POST] ==========

comments_data = []
analyzer = SentimentIntensityAnalyzer()  # Inisialisasi analisis sentimen

for link in post_links:
    driver.get(link)
    time.sleep(6)

    try:
        # Coba temukan div tempat komentar berada
        scroll_div = driver.find_element(By.CLASS_NAME, 'x5yr21d.xw2csxc.x1odjw0f.x1n2onr6')
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_div)

        # Loop untuk scroll komentar sampai habis
        while True:
            try:
                load_more = driver.find_element(By.XPATH, "//span[contains(text(), 'Load more comments')]")
                load_more.click()
                time.sleep(3)
            except NoSuchElementException:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_div)
                time.sleep(3)
                new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_div)
                if new_height == last_height:
                    break
                last_height = new_height

        # Ambil semua komentar
        comments = driver.find_elements(By.XPATH,
            "(//span[@class='x1lliihq x1plvlek xryxfnj x1n2onr6 x1ji0vk5 x18bv5gf x193iq5w "
            "xeuugli x1fj9vlw x13faqbe x1vvkbs x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty "
            "x1943h6x x1i0vuye xvs91rp xo1l8bm x5n08af x10wh9bi xpm28yp x8viiok x1o7cslx'])")

        # Ambil tanggal postingan
        try:
            post_date = driver.find_element(By.XPATH, "(//time[@class='x1p4m5qa'])").get_attribute("datetime")
            post_date = pd.to_datetime(post_date)
        except NoSuchElementException:
            post_date = None

        # Ambil jumlah likes
        try:
            likes_element = driver.find_element(By.XPATH,
                "//span[@class='html-span xdj266r x14z9mp xat24cr x1lziwak xexx8yu xyri2b "
                "x18d9i69 x1c1uobl x1hl2dhg x16tdsg8 x1vvkbs']")
            likes_text = likes_element.text.replace(",", "").strip()
            likes = int(likes_text) if likes_text.isdigit() else 0
        except NoSuchElementException:
            likes = 0

        # Proses tiap komentar
        for comment in comments:
            text = comment.text
            mentions_count = count_mentions(text)
            time.sleep(0.3)  # ⏳ Jeda sebelum translate untuk stabilitas
            translated_text = translate_comment(text)
            sentiment = analyzer.polarity_scores(translated_text or "no comment")

            comments_data.append({
                "post_url": link,
                "post_date": post_date,
                "comment": text,
                "translated_comment": translated_text,
                "likes": likes,
                "mentions": mentions_count,
                "neg": sentiment['neg'],
                "neu": sentiment['neu'],
                "pos": sentiment['pos'],
                "compound": sentiment['compound']
            })

    except Exception as e:
        print(f"❌ Error processing post {link}: {e}")
        traceback.print_exc()

# Tutup browser setelah scraping selesai
driver.quit()

# ========== [OLAH DATA & SIMPAN KE CSV] ==========

df = pd.DataFrame(comments_data)

# Klasifikasi sentimen berdasarkan nilai compound
df['sentiment_label'] = df['compound'].apply(
    lambda x: 'positive' if x >= 0.05 else 'negative' if x <= -0.05 else 'neutral'
)

# Simpan ke file CSV
df.to_csv("translated_comments_with_sentiment.csv", index=False, encoding='utf-8-sig')
print("✅ Data disimpan ke translated_comments_with_sentiment.csv")

# ========== [STATISTIK & VISUALISASI] ==========

# Distribusi jumlah komentar
sentiment_counts = df['sentiment_label'].value_counts(normalize=True) * 100
print("\n📊 Distribusi Sentimen (persentase):")
print(sentiment_counts)

# Rata-rata skor compound
compound_avg_per_category = df.groupby('sentiment_label')['compound'].mean()
print("\n📈 Rata-rata skor compound per kategori:")
print(compound_avg_per_category)

# Pie Chart
plt.figure(figsize=(6, 6))
df['sentiment_label'].value_counts().reindex(['positive', 'neutral', 'negative']).plot.pie(
    autopct='%1.1f%%',
    startangle=140,
    colors=['green', 'gray', 'red']
)
plt.title("Distribusi Sentimen (Pie Chart)")
plt.ylabel('')
plt.tight_layout()
plt.savefig("sentiment_pie_chart.png")
plt.show()

# Bar Chart Rata-rata Skor Compound
plt.figure(figsize=(6, 4))
compound_avg_per_category.reindex(['positive', 'neutral', 'negative']).plot(
    kind='bar',
    color=['green', 'gray', 'red']
)
plt.title("Rata-rata Skor Compound per Kategori Sentimen")
plt.ylabel("Skor Compound")
plt.xlabel("Kategori Sentimen")
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig("compound_avg_bar_chart.png")
plt.show()

