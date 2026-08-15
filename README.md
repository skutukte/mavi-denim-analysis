# Mavi — Denim Fit Satış Analizi

2024-02-01 → 2025-01-31 arası 34.070 satırlık denim satış verisi üzerinde uçtan uca veri
temizliği, keşifçi analiz ve BI-ready star schema üretimi.

**Temel ilke: hiçbir satır silinmedi.** 34.070 satır girer, 34.070 satır çıkar. Şüpheli
kayıtlar silinmek yerine bayrak kolonlarıyla işaretlenir, böylece her toplam ham veriyle
kuruşu kuruşuna mutabık kalır (net ciro **17.830.490,44 TL**).

---

## Hızlı başlangıç

```bash
pip install -r requirements.txt

cd src
python3 00_load.py
python3 01_clean.py
python3 02_eda.py
python3 03_trend.py
python3 04_category.py
python3 05_export_bi.py
```

Scriptler **idempotent**: baştan çalıştırıldığında PNG'ler dahil tüm çıktılar birebir aynı
üretilir. `data/raw/` salt okunurdur, hiçbir script oraya yazmaz.

---

## Pipeline

| Script | Ne yapar | Çıktı |
|---|---|---|
| `00_load.py` | Ham xlsx okuma, satır sayısı ve unique guard'ları | `data/interim/*_raw.parquet` |
| `01_clean.py` | **Tüm temizlik kararları.** Her adımda etkilenen satır sayısını basar | `data/interim/` star schema + `01_cleaning_report.csv` |
| `02_eda.py` | Dağılım, aykırı değer, iade, mağaza/fit/beden/saat kırılımları | 6 figür, 9 tablo |
| `03_trend.py` | 12 aylık gözlem, gün×saat yoğunluk, fit bazlı seyir | 5 figür, 8 tablo, mağaza×ay paneli |
| `04_category.py` | Fit × mağaza potansiyel skorlaması | 4 figür, 8 tablo |
| `05_export_bi.py` | snake_case star schema + veri sözlüğü | `data/processed/` |

`config.py` pipeline adımı değildir — ortak yol sabitleri, figür/tablo kaydetme ve
idempotent varsayım loglama yardımcılarını barındırır.

### Katman ayrımı

- `data/interim/` — dahili çalışma dosyaları, orijinal kolon adlarıyla (01-04 bunları okur)
- `data/processed/` — **BI katmanı**, snake_case, tek yazarı `05_export_bi.py`

Aynı dosya adının iki farklı kolon şemasıyla yazılmasını önlemek için tek yazar kuralı uygulanır.

---

## Veri temizliğinde alınan kararlar

Tam liste ve etkilenen satır sayıları: `outputs/tables/01_cleaning_report.csv`

1. **Analize uygun tek kırılım bulundu.** `Class` / `MainCategory` / `Category` / `SubCategory`
   kolonlarının dördü de tek değerli, analitik değeri sıfır. Kullanılabilir tek kırılım
   `SubCategoryClass` = **fit**.
2. **Fit etiketleri normalize edildi.** `Colored Denims` → `Renkli Denim`, `Maternity` → `Hamile`;
   5'ten az ürünlü 6 etiket `Other` altında toplandı. `*EN` kolonlarında 278-280 null olduğu için
   **eşleştirmede İngilizce kolonlar kullanılmadı**.
3. **Satış ve iade ayrıştırıldı.** 8.086 iade satırında tutar/adet negatif.
   Brüt 25,1M − İade 7,3M = **Net 17,8M TL**. İki seri hiçbir grafikte üst üste bindirilmedi.
4. **Anomaliler işaretlendi, silinmedi.** `ReturnFlag=0` olmasına rağmen `Amount<0` olan 15 satır
   `is_anomaly` ile işaretlenip toplamlarda bırakıldı → `01_anomalies.csv`.
5. **Gizli boyutlar türetildi.** Beden kodu `ProductItemCode`'dan çıkarıldı (71 beden, 34.070
   satırın tamamı çözüldü); `Time` alanındaki `903` → `09:03`.
6. **Varsayım kolon adına yazıldı.** `DiscountAmount` semantiği belirsiz; seçilen varsayım
   `assumed_gross_amount` kolon adında görünür kalıyor.

---

## Öne çıkan bulgular

Tam liste: [`notes/findings.md`](notes/findings.md)

**İade oranı yüksek.** Tutar bazlı **%29,0**, adet bazlı %31,1. Tutar oranının adet oranından
düşük olması, iade edilenlerin ortalamada satılanlardan daha ucuz olduğunu gösteriyor.

**Ciro beklenenden homojen.** 350 mağazanın en iyi 20'si net cironun yalnızca %16,4'ünü,
ilk %20'lik dilim (70 mağaza) %43'ünü üretiyor — klasik 80/20 yoğunlaşmasından uzak.

**Fit payları sert kayıyor ama sebebi ayrıştırılamıyor.** Straight ilk 3 aya kıyasla son 3 ayda
+31,6 puan kazanmış, Slim Straight −30,3 puan kaybetmiş. Ancak satışı olan 249 üründen yalnızca
**23'ünün** (%9) 12 ay boyunca kesintisiz satışı var — bu kayma tüketici tercihinden mi asortiman
kararından mı geliyor, bu veriyle ayrılamaz.

**Potansiyel: Straight ve Baggy.** Fit bazlı potansiyel skorunda Straight 80/100, Baggy 76/100.
Baggy cironun sadece %5,7'si ama en hızlı büyüyen ve iadesi en düşük fit — klasik ciro
sıralamasında görünmeyen bir alan. Skor tanımı ve ağırlıkları: `04_scoring_definition.csv`.

**Zaman kırılımı aksiyon alınabilir.** Zirve saat 17:00, en güçlü gün Pazar, hafta sonu iki günde
net cironun %42'si dönüyor.

---

## Bilinçli sınırlar

Veride olmayan hiçbir şey iddia edilmedi. Üç sınır açıkça raporlandı:

| Sınır | Sebep | Ne yapıldı |
|---|---|---|
| **Lokasyon analizi yok** | Şehir/bölge/mağaza tipi kolonu veride mevcut değil | "Lokasyon" = mağaza bazlı analiz. `dim_store` coğrafi değil, satış davranışından türetilmiş |
| **Ortalama sepet hesaplanamıyor** | Fiş/sepet kimliği yok; `DocID` satır başına unique. Saate göre gruplayınca grupların %99'u tek kalem | "Ortalama sepet" yerine `avg_line_amount` raporlandı → `03_basket_feasibility.csv` |
| **Mevsimsellik doğrulanamıyor** | Tek bir 12 aylık döngü var, her takvim ayının 1 gözlemi | "Trend" değil **"12 aylık gözlem"** terimi kullanıldı. Mevsimsellik için ≥24-36 ay gerekir |

Ayrıca `04`'teki iskonto bileşeni doğrulanmamış varsayıma dayandığı için skor bu bileşen olmadan
da hesaplandı: genel sıralama sağlam (Spearman 0,95) ama ilk 20 hücrenin yalnızca 10'u ortak.
Aksiyon almadan önce `DiscountAmount`'ın gerçek tanımı teyit edilmeli.

Her varsayım tek satır olarak: [`notes/assumptions.md`](notes/assumptions.md)

---

## BI katmanı

`data/processed/` altındaki star schema doğrudan PowerBI/Tableau'ya bağlanabilir.
Kolon açıklamaları: `outputs/tables/05_data_dictionary.csv`

```
fact_sales (34.070)
  ├── store_code    → dim_store   (350)
  ├── product_code  → dim_product (1.511)
  └── sale_date     → dim_date    (366, kesintisiz takvim)

panel_store_month (4.200)   mağaza × ay dengeli panel — tahminleme modelinin girdisi
```

Üç join da 0 yetim anahtarla doğrulanır (`05_export_bi.py` içinde assert).

**BI kurulumunda dikkat:**

- `size_code` **metin olarak import edilmeli** — baştaki sıfır anlamlı (`007` ≠ `7`).
  CSV'de doğru yazılıyor ama tip çıkarımı bunu sayıya çevirirse bedenler birleşir.
- Kırılım için `dim_product.fit` kullanılmalı; `class_name` / `main_category` / `category` /
  `sub_category` tek değerlidir, `*_en` kolonları nulldur.
- `fact_sales.amount` işaretlidir (iadede negatif) → toplamı **net ciro** verir.
  Brüt ve iade ayrı istenirse `sales_amount` / `return_amount` kolonları hazır.

---

## Veri seti

| | |
|---|---|
| Dönem | 2024-02-01 → 2025-01-31 (366 gün, tam 12 ay) |
| Satır | 34.070 satış kalemi |
| Mağaza | 350 |
| Ürün | 1.511 tanımlı, 249'unun satışı var |
| Beden | 71 (türetilmiş) |
| Fit | 11 normalize etiket, 10'unun satışı var |
| Brüt ASP | 965,29 TL |
