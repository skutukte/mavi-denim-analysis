"""01 — Temizlik ve BI-ready star schema üretimi.

Hiçbir satır SİLİNMEZ. Şüpheli kayıtlar sadece bayrak kolonlarıyla işaretlenir,
toplamlar ham veriyle birebir tutmaya devam eder.

Input : data/interim/sales_raw.parquet
        data/interim/products_raw.parquet
Output: data/interim/sales_clean.parquet          (denormalize ara tablo)
        data/interim/fact_sales.parquet           (dahili star schema — 02-04 okur)
        data/interim/dim_product.parquet
        data/interim/dim_date.parquet
        outputs/tables/01_cleaning_report.csv
        outputs/tables/01_anomalies.csv
        outputs/tables/01_subcategoryclass_mapping.csv
        notes/assumptions.md
"""

import numpy as np
import pandas as pd

import config as cfg

# TR/EN karışık fit etiketleri — aynı şeyi ifade edenler TR tarafına toplanır.
# EN kolonlarında 278-280 null olduğu için anahtar olarak *EN kolonları KULLANILMAZ.
FIT_LABEL_MAP = {
    "Colored Denims": "Renkli Denim",
    "Maternity": "Hamile",
}

# Bu eşiğin altında ürünü olan fit etiketleri "Other" altında toplanır (CLAUDE.md).
RARE_FIT_THRESHOLD = 5
OTHER_LABEL = "Other"

# Tek değerli oldukları doğrulanmış, analitik değeri olmayan kolonlar.
DEAD_CATEGORY_COLS = ["Class", "MainCategory", "Category", "SubCategory"]

MONTH_NAMES_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}
DAY_NAMES_TR = {
    0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
    4: "Cuma", 5: "Cumartesi", 6: "Pazar",
}

_report: list[dict] = []


def step(no: str, rule: str, affected: int, total: int, note: str = "") -> None:
    """Temizlik adımını hem konsola yazar hem rapora ekler."""
    pct = f"{affected / total * 100:.2f}%" if total else "-"
    print(f"  [{no}] {rule}: {affected:,} satır etkilendi ({pct}) {note}")
    _report.append(
        {"step": no, "rule": rule, "affected_rows": affected, "total_rows": total,
         "affected_pct": pct, "note": note}
    )


# --------------------------------------------------------------------------
# Ürün boyutu
# --------------------------------------------------------------------------
def build_dim_product(products: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SubCategoryClass'ı normalize eder, seyrek etiketleri Other'a toplar."""
    print("\n-- Ürün boyutu (dim_product) --")
    dim = products.copy()
    raw_label = dim["SubCategoryClass"]

    # 1) TR/EN eşanlamlı etiketleri birleştir
    normalized = raw_label.replace(FIT_LABEL_MAP)
    merged = int((normalized != raw_label).sum())
    step("03a", "Fit etiketi TR/EN birleştirme", merged, len(dim),
         f"eşleşen: {', '.join(f'{k}→{v}' for k, v in FIT_LABEL_MAP.items())}")

    # 2) Ürün sayısı eşiğin altındaki etiketleri Other'a topla
    counts = normalized.value_counts()
    rare = counts[counts < RARE_FIT_THRESHOLD].index.tolist()
    final = normalized.where(~normalized.isin(rare), OTHER_LABEL)
    bucketed = int((final != normalized).sum())
    step("03b", f"{RARE_FIT_THRESHOLD}'ten az ürünlü fit → {OTHER_LABEL}", bucketed, len(dim),
         f"toplanan etiketler: {', '.join(sorted(rare)) if rare else 'yok'}")

    dim["fit"] = final

    # Kayıp kontrolü: normalizasyon satır kaybetmemeli
    assert len(dim) == len(products), "dim_product satır sayısı değişti"
    assert dim["fit"].notna().all(), "fit kolonunda null var"

    # Etiket eşleme tablosu — ham etiketin nereye gittiği izlenebilir olsun
    mapping = (
        pd.DataFrame({"raw_label": raw_label, "normalized_label": normalized, "final_fit": final})
        .value_counts()
        .reset_index(name="n_products")
        .sort_values(["final_fit", "n_products"], ascending=[True, False])
    )

    # Tek değerli ölü kolonları raporla ama dim'de tut (izlenebilirlik)
    for col in DEAD_CATEGORY_COLS:
        n_unique = dim[col].nunique()
        step("09", f"Tek değerli kolon tespiti: {col}", len(dim) if n_unique == 1 else 0, len(dim),
             f"{n_unique} farklı değer ({dim[col].iloc[0]}) — kırılımda kullanılmayacak")

    return dim, mapping


# --------------------------------------------------------------------------
# Tarih boyutu
# --------------------------------------------------------------------------
def build_dim_date(dates: pd.Series) -> pd.DataFrame:
    """Satış tarihi aralığını kapsayan kesintisiz takvim tablosu."""
    print("\n-- Tarih boyutu (dim_date) --")
    full = pd.date_range(dates.min(), dates.max(), freq="D")
    dim = pd.DataFrame({"Date": full})
    dim["year"] = dim.Date.dt.year
    dim["month"] = dim.Date.dt.month
    dim["year_month"] = dim.Date.dt.strftime("%Y-%m")
    dim["month_name_tr"] = dim.month.map(MONTH_NAMES_TR)
    dim["day"] = dim.Date.dt.day
    dim["day_of_week"] = dim.Date.dt.dayofweek
    dim["day_name_tr"] = dim.day_of_week.map(DAY_NAMES_TR)
    dim["iso_week"] = dim.Date.dt.isocalendar().week.astype(int)
    dim["is_weekend"] = dim.day_of_week >= 5

    n_missing = len(full) - dates.nunique()
    print(f"  Aralık: {full.min().date()} → {full.max().date()}  ({len(full)} gün)")
    step("01c", "Satış olmayan takvim günü", n_missing, len(full),
         "dim_date kesintisiz, fact'te karşılığı yok")
    return dim


# --------------------------------------------------------------------------
# Ana temizlik
# --------------------------------------------------------------------------
def main() -> None:
    cfg.header("01 — TEMİZLİK VE STAR SCHEMA")
    cfg.ensure_dirs()

    sales = pd.read_parquet(cfg.INTERIM / "sales_raw.parquet")
    products = pd.read_parquet(cfg.INTERIM / "products_raw.parquet")
    n = len(sales)
    amount_before = sales["Amount"].sum()
    print(f"Girdi: {n:,} satış satırı, {len(products):,} ürün")

    df = sales.copy()

    print("\n-- Satış satırı temizliği --")

    # 1) Tarih: openpyxl serial'i datetime'a çeviriyor; çevirmediyse elle çevir.
    if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Date"] = pd.to_datetime(df["Date"], unit="D", origin="1899-12-30")
        step("01a", "Excel serial → datetime dönüşümü", n, n, "manuel dönüşüm uygulandı")
    else:
        step("01a", "Excel serial → datetime dönüşümü", 0, n,
             "openpyxl zaten datetime döndürdü, dönüşüm gereksiz")
    df["Date"] = df["Date"].dt.normalize()
    out_of_range = int(((df.Date < "2024-02-01") | (df.Date > "2025-01-31")).sum())
    step("01b", "Beklenen tarih aralığı dışı satır", out_of_range, n, "2024-02-01 → 2025-01-31")
    assert out_of_range == 0, "Tarih aralığı dışı satır var"

    # 2) Saat: Time int HHMM formatında (903 = 09:03). Sıfır padding gerekiyor.
    df["hour"] = df["Time"] // 100
    df["minute"] = df["Time"] % 100
    df["time_str"] = df["Time"].astype(str).str.zfill(4).str[:2] + ":" + \
                     df["Time"].astype(str).str.zfill(4).str[2:]
    padded = int((df["Time"] < 1000).sum())
    step("02a", "Sıfır padding gereken Time değeri", padded, n, "HHMM → HH:MM")
    bad_time = int(((df.hour < 0) | (df.hour > 23) | (df.minute > 59)).sum())
    step("02b", "Geçersiz saat/dakika", bad_time, n, f"saat aralığı: {df.hour.min()}-{df.hour.max()}")
    assert bad_time == 0, "Geçersiz Time değeri var"

    # 3) Ürün join'i (fit etiketi normalize edilmiş haliyle gelir)
    dim_product, fit_mapping = build_dim_product(products)

    print("\n-- Join --")
    df = df.merge(
        dim_product[["ProductCode", "fit", "SubCategoryClass"]],
        on="ProductCode", how="left", validate="many_to_one",
    )
    orphans = int(df["fit"].isna().sum())
    step("10", "Products'ta karşılığı olmayan satış satırı (orphan)", orphans, n, "beklenen: 0")
    assert orphans == 0, "Orphan satış satırı var"

    # 4) Beden kodu: ProductItemCode = ProductCode + 3 haneli beden eki.
    #    ProductCode formatı değişken (tireli/tiresiz) → sabit slice DEĞİL, prefix strip.
    print("\n-- Beden kodu --")
    prefix_ok = df.apply(lambda r: r.ProductItemCode.startswith(r.ProductCode), axis=1)
    step("04a", "ProductItemCode, ProductCode ile başlamıyor", int((~prefix_ok).sum()), n)
    df["size_code"] = [
        item[len(code):] if ok else None
        for item, code, ok in zip(df.ProductItemCode, df.ProductCode, prefix_ok)
    ]
    bad_size = int(df["size_code"].isna().sum() + (df["size_code"].str.len() != 3).sum())
    step("04b", "3 haneye çözülemeyen beden kodu", bad_size, n,
         f"{df['size_code'].nunique()} farklı beden kodu türetildi")

    # 5) İade ve anomali bayrakları — SATIR SİLİNMEZ
    print("\n-- Bayraklar --")
    df["is_return"] = df["ReturnFlag"] == 1
    step("05a", "İade satırı (ReturnFlag=1)", int(df.is_return.sum()), n,
         "Quantity ve Amount negatif")

    df["is_anomaly"] = (df["ReturnFlag"] == 0) & (df["Amount"] < 0)
    step("05b", "ANOMALİ: ReturnFlag=0 ama Amount<0", int(df.is_anomaly.sum()), n,
         "silinmedi, işaretlendi, toplamlarda kalıyor")

    inconsistent_return = int((df.is_return & (df.Amount > 0)).sum())
    step("05c", "İade işaretli ama Amount pozitif", inconsistent_return, n, "beklenen: 0")

    # 6) İskonto — semantiği belirsiz, VARSAYIM uygulanıyor
    print("\n-- İskonto (varsayımsal) --")
    df["assumed_gross_amount"] = df["Amount"] + df["DiscountAmount"]
    # Karşılaştırma sadece satış satırlarında anlamlı; iadede Amount negatif.
    df["discount_gt_amount"] = (~df.is_return) & (df.DiscountAmount > df.Amount)
    step("06a", "Satış satırında DiscountAmount > Amount", int(df.discount_gt_amount.sum()), n,
         "iskonto tanımıyla çelişiyor, işaretlendi")
    n_disc_gt_return = int((df.is_return & (df.DiscountAmount > df.Amount)).sum())
    step("06b", "İade satırında DiscountAmount > Amount", n_disc_gt_return, n,
         "Amount negatif olduğu için beklenen davranış, anomali değil")
    df["discount_negative"] = df["DiscountAmount"] < 0
    n_neg_sale = int((df.discount_negative & ~df.is_return).sum())
    step("06c", "Negatif DiscountAmount", int(df.discount_negative.sum()), n,
         f"tamamı iade satırında (satış satırında: {n_neg_sale})")

    # 7) Metrik konvansiyonu: iade tutarları zaten negatif → net = Amount toplamı
    df["sales_amount"] = df["Amount"].where(~df.is_return, 0.0)
    df["return_amount"] = df["Amount"].where(df.is_return, 0.0)
    df["sales_qty"] = df["Quantity"].where(~df.is_return, 0)
    df["return_qty"] = df["Quantity"].where(df.is_return, 0)
    df["year_month"] = df["Date"].dt.strftime("%Y-%m")

    # 8) ChangeCardFlag: semantiği belgesiz, taşınır ama analiz edilmez
    step("08", "ChangeCardFlag=1 satır", int((df.ChangeCardFlag == 1).sum()), n,
         "semantiği doğrulanmadı, fact'e taşındı, analiz edilmiyor")

    # --- Bütünlük kontrolleri ---
    print("\n-- Bütünlük kontrolleri --")
    assert len(df) == n, f"Satır sayısı değişti: {len(df)} != {n}"
    assert np.isclose(df["Amount"].sum(), amount_before), "Amount toplamı değişti"
    assert np.isclose(df.sales_amount.sum() + df.return_amount.sum(), amount_before), \
        "sales_amount + return_amount != toplam Amount"
    print(f"  Satır sayısı korundu: {len(df):,}")
    print(f"  Amount toplamı korundu: {df['Amount'].sum():,.2f}")

    dim_date = build_dim_date(df["Date"])

    # --- Çıktılar ---
    print("\n-- Çıktılar --")
    cfg.save_dataset(df, "sales_clean", folder=cfg.INTERIM, csv=False)

    fact_cols = [
        "DocID", "StoreCode", "ProductCode", "ProductItemCode", "size_code",
        "Date", "year_month", "hour", "minute", "time_str",
        "Quantity", "Amount", "DiscountAmount", "assumed_gross_amount",
        "sales_amount", "return_amount", "sales_qty", "return_qty",
        "ReturnFlag", "is_return", "is_anomaly",
        "discount_gt_amount", "discount_negative", "ChangeCardFlag",
    ]
    # Dahili star schema: 02-04 bunları okur, orijinal kolon adlarıyla.
    # BI'a gidecek snake_case sürümü 05_export_bi.py data/processed/ altına yazar.
    cfg.save_dataset(df[fact_cols], "fact_sales", folder=cfg.INTERIM, csv=False)
    cfg.save_dataset(dim_product, "dim_product", folder=cfg.INTERIM, csv=False)
    cfg.save_dataset(dim_date, "dim_date", folder=cfg.INTERIM, csv=False)

    cfg.save_table(pd.DataFrame(_report), "01_cleaning_report")
    cfg.save_table(df[df.is_anomaly][fact_cols], "01_anomalies")
    cfg.save_table(fit_mapping, "01_subcategoryclass_mapping")

    # --- Varsayımlar ---
    cfg.log_assumption(
        "İskonto semantiği belirsiz. VARSAYIM: `Amount` net (iskonto sonrası) tutardır ve "
        "brüt = Amount + DiscountAmount. Türetilen kolon bilinçli olarak `assumed_gross_amount` "
        "adıyla üretildi ki varsayım BI tarafında da görünür kalsın. Doğrulanmadı."
    )
    cfg.log_assumption(
        f"ReturnFlag=0 olmasına rağmen Amount<0 olan {int(df.is_anomaly.sum())} satır anomalidir. "
        "Karar: silinmedi, `is_anomaly` ile işaretlendi ve headline KPI'lara DAHİL edildi — "
        "böylece toplamlar ham veriyle birebir mutabık kalıyor. Detay: outputs/tables/01_anomalies.csv"
    )
    cfg.log_assumption(
        "`ChangeCardFlag` kolonu CLAUDE.md'de tanımlı değil ve semantiği doğrulanamadı. "
        "Karar: fact_sales'e taşındı, üzerine hiçbir analiz kurulmadı, sunuma sayı girmiyor."
    )
    cfg.log_assumption(
        "Fit etiketleri TR tarafına normalize edildi (Colored Denims→Renkli Denim, "
        f"Maternity→Hamile). {RARE_FIT_THRESHOLD}'ten az ürünü olan etiketler `Other` altında "
        "toplandı. `*EN` kolonlarında 278-280 null olduğu için join/label anahtarı olarak "
        "kullanılmadı; kendi mapping dict'imiz üzerinden gidildi."
    )
    cfg.log_assumption(
        "Beden kodu `ProductItemCode`'dan `ProductCode` prefix'i çıkarılarak türetildi. "
        "Sabit karakter kesme kullanılmadı çünkü ProductCode iki farklı formatta "
        "(M1020589168 tiresiz / M1011043-90090 tireli). 34.070 satırın tamamı 3 haneye çözüldü."
    )
    cfg.log_assumption(
        "`size_code` baştaki sıfırları anlamlı olan bir metin kolonudur ('007' ≠ 7). Parquet bunu "
        "string olarak saklar; CSV'de tip bilgisi olmadığı için BI tool'unda bu kolon metin olarak "
        "içe aktarılmalıdır, aksi halde baştaki sıfırlar kaybolur ve bedenler birleşir."
    )
    cfg.log_assumption(
        "Lokasyon boyutu olarak yalnızca `StoreCode` mevcut; şehir/bölge/mağaza tipi kolonu "
        "veri setinde YOK. Bu nedenle 'lokasyon bazlı analiz' = mağaza bazlı analizdir. "
        "05'te üretilen `dim_store` COĞRAFİ DEĞİL, tamamen satış davranışından TÜRETİLMİŞ "
        "özellikler içerir (ciro dilimi, aktif ay sayısı, iade oranı, baskın fit)."
    )
    cfg.log_assumption(
        "Class / MainCategory / Category / SubCategory kolonlarının hepsi tek değerlidir; "
        "izlenebilirlik için dim_product'ta tutuldu ama hiçbir kırılımda kullanılmadı."
    )
    cfg.log_assumption(
        "İade satırlarında Amount zaten negatif olduğu için metrik konvansiyonu: "
        "net = sum(Amount), brüt satış = sum(Amount[~is_return]), iade = sum(Amount[is_return]). "
        "Bu üç tanım tüm downstream script'lerde aynı anlamda kullanılır."
    )

    print(f"\n01 tamamlandı. notes/assumptions.md güncellendi.")


if __name__ == "__main__":
    main()
