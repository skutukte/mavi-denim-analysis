# Mavi — Denim Fit Sales Analysis

## Görev
Ek görev teslimi. Python ile veri temizliği + EDA, bir BI toolunda görselleştirme,
sonuç olarak PDF sunum. Sunumda 3 başlık olacak:
1. Data manipülasyonu / temizliğinde dikkat edilen noktalar
2. Analiz çıktıları + ekran görüntüleri
3. Ay / lokasyon bazlı tahminleme modeli için izlenecek yol (model kurulmayacak, yol anlatılacak)

## Repo yapısı
```
data/raw/        Mavi_Data_Analytics_Denim_Fit_Sales_Analysis.xlsx  (asla değiştirme)
data/interim/    ara parquet çıktıları
data/processed/  BI toolunun okuyacağı final CSV/parquet
src/             00_load.py 01_clean.py 02_eda.py 03_trend.py 04_category.py
outputs/figures/ PNG grafikler
outputs/tables/  CSV özet tablolar
notes/           assumptions.md, findings.md
```

## Veri gerçekleri (doğrulandı, tekrar kontrol etmene gerek yok)

**Sales** — 34.070 satır, 11 kolon, hiç null yok, tam duplicate yok, DocID unique.
Tarih aralığı 2024-02-01 → 2025-01-31 (tam 12 ay). 350 farklı StoreCode.

**Products** — 1.511 satır, ProductCode unique. Sales→Products join %100 eşleşiyor
(orphan kayıt yok).

### Dikkat edilecek noktalar
- `Class`, `MainCategory`, `Category`, `SubCategory` kolonlarının **hepsi tek değerli**
  (hepsi "Denim All" / "Denim Pantolon" / "Ticari Malzemeler"). Analitik değeri sıfır.
  **Tek anlamlı kategori kırılımı `SubCategoryClass` = fit** (Wide Leg, Flare, Straight,
  Skinny, Mom, Slim Straight, Super Skinny, Boyfriend, Baggy + uzun kuyruk).
- `SubCategoryClass` içinde TR/EN karışık etiketler var ve bunlar aynı şeyi ifade ediyor:
  `Renkli Denim` ↔ `Colored Denims`, `Hamile` ↔ `Maternity`, ayrıca `Büyük Beden`,
  `Denim All`. Bunları normalize et; 5'ten az kayıtlı olanları `Other` altında topla
  ama toplamı kaybetme.
- `*EN` kolonlarında 278–280 null var. **Join ya da label anahtarı olarak EN kolonlarını
  kullanma.** TR kolon + kendi mapping dict'in üzerinden git.
- `ReturnFlag=1` → Quantity ve Amount negatif (8.086 satır, tutarlı).
  **AMA 15 satırda `ReturnFlag=0` olmasına rağmen `Amount < 0`.** Bunlar anomali;
  sil değil, işaretle ve `notes/assumptions.md`'ye yaz.
- `DiscountAmount` semantiği belirsiz. 301 satırda DiscountAmount > Amount, bazı satırlarda
  negatif. Muhtemelen `Amount` net (iskonto sonrası) ve gross = Amount + DiscountAmount —
  **ama bu bir varsayım, doğrulanmadı.** Hangi tanımı seçtiysen sunumda açıkça belirt.
- `Time` int olarak HHMM formatında (903 = 09:03, 2353 = 23:53). Sıfır padding lazım.
  Saat bazlı analiz için `Time // 100` yeterli.
- `ProductItemCode` = `ProductCode` + 3 haneli beden eki (%100 türetilebilir, doğrulandı).
  Bu ekten **beden boyutu** üretilebilir — 71 farklı beden kodu var. Katma değerli kırılım.
- **Lokasyon için sadece `StoreCode` var.** Şehir/bölge/mağaza tipi kolonu YOK.
  "Lokasyon bazlı" analiz = mağaza bazlı. Bu limiti sunumda dürüstçe belirt.

## Kurallar
- `data/raw/` read-only. Hiçbir script raw dosyaya yazmaz.
- Her script idempotent olsun, baştan çalıştırılabilsin.
- **Sayı uydurma.** Sunuma girecek her rakam bir script çıktısından gelecek ve
  `outputs/tables/` altına CSV olarak kaydedilecek.
- Attığın her varsayımı `notes/assumptions.md`'ye tek satır olarak ekle.
- Her grafik hem ekrana değil, `outputs/figures/` altına PNG olarak kaydedilsin (dpi=150).
- İade ve satış metriklerini ayrı ayrı raporla. Net = brüt satış - iade.
  Aynı grafikte karıştırma.
- Yorum satırları ve print'ler Türkçe, kod/değişken isimleri İngilizce.

## BI tool sınırı
Claude Code PowerBI/Tableau/Qlik dosyası üretemez. Claude Code'un işi:
`data/processed/` altına temiz, BI-ready tablolar çıkarmak
(fact_sales + dim_product + dim_date). Dashboard'u sen kuracaksın.
