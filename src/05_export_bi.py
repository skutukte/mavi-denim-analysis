"""05 — BI export katmanı: star schema.

Bu script pipeline'ın TEK BI-facing çıktı sahibidir. 01-04 dahili çalışma
dosyalarını `data/interim/` altında orijinal kolon adlarıyla tutar; 05 bunları
okur, snake_case'e çevirir ve `data/processed/` altına BI toolunun okuyacağı
final tabloları yazar.

Neden iki katman: aynı dosya adının farklı kolon adlarıyla iki kez yazılması
(01'in `fact_sales.csv`'si ile 05'inki) sessiz bir tuzak olurdu. Tek yazar kuralı.

ŞEMA (star)
    fact_sales   — grain: 1 satır = 1 satış kalemi (doc_id unique)
      ├─ store_code    → dim_store.store_code
      ├─ product_code  → dim_product.product_code
      └─ sale_date     → dim_date.date

Input : data/interim/fact_sales.parquet, dim_product.parquet, dim_date.parquet
        data/interim/panel_store_month.parquet
Output: data/processed/fact_sales.csv    + .parquet
        data/processed/dim_product.csv   + .parquet
        data/processed/dim_date.csv      + .parquet
        data/processed/dim_store.csv     + .parquet
        data/processed/panel_store_month.csv + .parquet  (modelleme girdisi)
        outputs/tables/05_data_dictionary.csv
        outputs/tables/05_export_summary.csv
"""

import numpy as np
import pandas as pd

import config as cfg

# Takvim sınırları sabit — veriye göre değil, göreve göre.
# Böylece satışsız günler de dim_date'te yer alır.
CALENDAR_START = "2024-02-01"
CALENDAR_END = "2025-01-31"

MONTH_NAMES_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}
DAY_NAMES_TR = {
    0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
    4: "Cuma", 5: "Cumartesi", 6: "Pazar",
}

# --- snake_case kolon eşlemeleri -------------------------------------------
FACT_RENAME = {
    "DocID": "doc_id",
    "StoreCode": "store_code",
    "ProductCode": "product_code",
    "ProductItemCode": "product_item_code",
    "size_code": "size_code",
    "Date": "sale_date",
    "year_month": "year_month",
    "hour": "sale_hour",
    "minute": "sale_minute",
    "time_str": "sale_time",
    "Quantity": "quantity",
    "Amount": "amount",
    "DiscountAmount": "discount_amount",
    "assumed_gross_amount": "assumed_gross_amount",
    "sales_amount": "sales_amount",
    "return_amount": "return_amount",
    "sales_qty": "sales_quantity",
    "return_qty": "return_quantity",
    "ReturnFlag": "return_flag",
    "is_return": "is_return",
    "is_anomaly": "is_anomaly",
    "discount_gt_amount": "is_discount_gt_amount",
    "discount_negative": "is_discount_negative",
    "ChangeCardFlag": "change_card_flag",
}

PRODUCT_RENAME = {
    "ProductCode": "product_code",
    "fit": "fit",
    "SubCategoryClass": "sub_category_class_raw",
    "Class": "class_name",
    "MainCategory": "main_category",
    "Category": "category",
    "SubCategory": "sub_category",
    "MainCategoryEN": "main_category_en",
    "CategoryEN": "category_en",
    "SubCategoryEN": "sub_category_en",
    "SubCategoryClassEN": "sub_category_class_en",
}

PANEL_RENAME = {
    "StoreCode": "store_code",
    "year_month": "year_month",
    "net_sales": "net_sales",
    "gross_sales": "gross_sales",
    "return_amount": "return_amount",
    "net_qty": "net_quantity",
    "n_rows": "n_transactions",
    "had_sales": "had_sales",
}

# --- Veri sözlüğü: her kolon için tek satır açıklama ------------------------
DICTIONARY = {
    "fact_sales": {
        "doc_id": "Birincil anahtar. Satır başına unique — fiş/sepet kimliği DEĞİLDİR.",
        "store_code": "dim_store'a yabancı anahtar.",
        "product_code": "dim_product'a yabancı anahtar.",
        "product_item_code": "product_code + 3 haneli beden eki.",
        "size_code": "METİN. Baştaki sıfır anlamlıdır ('007' ≠ 7) — BI'da metin olarak import edin.",
        "sale_date": "dim_date'e yabancı anahtar (gün seviyesi).",
        "year_month": "YYYY-MM. Aylık kırılımlar için hazır anahtar.",
        "sale_hour": "İşlem saati 0-23 (veride 9-23 aralığında).",
        "sale_minute": "İşlem dakikası 0-59.",
        "sale_time": "HH:MM biçiminde sıfır dolgulu saat.",
        "quantity": "İŞARETLİ adet. İade satırlarında negatif.",
        "amount": "İŞARETLİ tutar. İade satırlarında negatif. TOPLAMI = NET CİRO.",
        "discount_amount": "Ham iskonto tutarı. Semantiği doğrulanmadı.",
        "assumed_gross_amount": "VARSAYIMSAL brüt = amount + discount_amount. Doğrulanmadı.",
        "sales_amount": "Yalnızca satış satırlarında amount, iadede 0. Brüt satış toplamı için.",
        "return_amount": "Yalnızca iade satırlarında amount (negatif), satışta 0.",
        "sales_quantity": "Yalnızca satış satırlarında quantity, iadede 0.",
        "return_quantity": "Yalnızca iade satırlarında quantity (negatif), satışta 0.",
        "return_flag": "Kaynak sistemden gelen ham bayrak (0/1).",
        "is_return": "return_flag = 1 (boolean).",
        "is_anomaly": "return_flag=0 olmasına rağmen amount<0. 15 satır. Toplamlara DAHİL.",
        "is_discount_gt_amount": "Satış satırında discount_amount > amount. 278 satır.",
        "is_discount_negative": "discount_amount < 0. Tamamı iade satırında.",
        "change_card_flag": "Kaynak sistemden gelen ham bayrak. SEMANTİĞİ BİLİNMİYOR, analiz edilmedi.",
    },
    "dim_product": {
        "product_code": "Birincil anahtar. 1.511 ürün, unique.",
        "fit": "NORMALİZE fit etiketi. Tek anlamlı kategori kırılımı budur. Kırılımlarda BUNU kullanın.",
        "sub_category_class_raw": "Ham fit etiketi (TR/EN karışık, normalize edilmemiş). Denetim içindir.",
        "class_name": "TEK DEĞERLİ ('Ticari Malzemeler') — kırılımda kullanmayın.",
        "main_category": "TEK DEĞERLİ ('Denim All') — kırılımda kullanmayın.",
        "category": "TEK DEĞERLİ ('Denim All') — kırılımda kullanmayın.",
        "sub_category": "TEK DEĞERLİ ('Denim Pantolon') — kırılımda kullanmayın.",
        "main_category_en": "İngilizce karşılık. 278 NULL — anahtar olarak kullanmayın.",
        "category_en": "İngilizce karşılık. 278 NULL — anahtar olarak kullanmayın.",
        "sub_category_en": "İngilizce karşılık. 280 NULL — anahtar olarak kullanmayın.",
        "sub_category_class_en": "İngilizce fit. 280 NULL — anahtar olarak kullanmayın.",
    },
    "dim_date": {
        "date": "Birincil anahtar. 2024-02-01 → 2025-01-31 KESİNTİSİZ takvim (366 gün).",
        "year": "Takvim yılı.",
        "quarter": "Takvim çeyreği 1-4.",
        "month": "Ay numarası 1-12.",
        "year_month": "YYYY-MM.",
        "month_name_tr": "Türkçe ay adı.",
        "day": "Ayın günü.",
        "day_of_year": "Yılın kaçıncı günü.",
        "day_of_week": "0=Pazartesi … 6=Pazar.",
        "day_name_tr": "Türkçe gün adı.",
        "iso_week": "ISO hafta numarası.",
        "iso_year_week": "YYYY-Www biçiminde ISO hafta anahtarı.",
        "is_weekend": "Cumartesi veya Pazar.",
        "is_month_end": "Ayın son günü.",
        "has_sales": "O gün fact_sales'te en az bir satır var mı.",
    },
    "dim_store": {
        "store_code": "Birincil anahtar. 350 mağaza.",
        "net_sales": "Dönem toplam net cirosu (12 ay).",
        "gross_sales": "Dönem brüt satışı (iade hariç).",
        "return_amount": "Dönem iade tutarı (negatif).",
        "return_rate_amount": "|iade| / brüt satış.",
        "net_quantity": "Dönem net adedi.",
        "n_transactions": "Dönem işlem satırı sayısı.",
        "avg_line_amount": "net_sales / n_transactions. SEPET DEĞİLDİR — fiş kimliği yok.",
        "revenue_rank": "Net ciroya göre sıra (1 = en yüksek).",
        "revenue_share_pct": "Toplam net ciro içindeki pay (%).",
        "revenue_tier": "Kümülatif ciroya göre A (ilk %50), B (%50-80), C (kalan).",
        "active_months": "Satış görülen ay sayısı (0-12).",
        "first_sale_date": "İlk satış günü.",
        "last_sale_date": "Son satış günü.",
        "top_fit": "Mağazada net cirosu en yüksek fit.",
        "top_fit_share_pct": "top_fit'in o mağazanın net cirosundaki payı (%).",
        "NOT": "COĞRAFİ BİLGİ YOKTUR. Şehir/bölge/mağaza tipi kolonu kaynak veride mevcut değil; "
               "buradaki tüm özellikler satış davranışından TÜRETİLMİŞTİR.",
    },
}


def to_dictionary_rows(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Veri sözlüğünü gerçek şemayla eşleştirerek üretir."""
    rows = []
    for table, df in frames.items():
        for col in df.columns:
            rows.append({
                "table": table,
                "column": col,
                "dtype": str(df[col].dtype),
                "n_null": int(df[col].isna().sum()),
                "description": DICTIONARY.get(table, {}).get(col, ""),
            })
        # Tabloya özel serbest not (kolon değil)
        note = DICTIONARY.get(table, {}).get("NOT")
        if note:
            rows.append({"table": table, "column": "(tablo notu)", "dtype": "", "n_null": 0,
                         "description": note})
    d = pd.DataFrame(rows)
    missing = d[(d.description == "") & (d.column != "(tablo notu)")]
    assert missing.empty, f"Veri sözlüğünde açıklaması olmayan kolon: {missing.column.tolist()}"
    return d


# --------------------------------------------------------------------------
def build_dim_date(fact: pd.DataFrame) -> pd.DataFrame:
    """2024-02-01 → 2025-01-31 KESİNTİSİZ takvim; satışsız günler dahil."""
    print("\n-- dim_date --")
    rng = pd.date_range(CALENDAR_START, CALENDAR_END, freq="D")
    d = pd.DataFrame({"date": rng})
    d["year"] = d.date.dt.year
    d["quarter"] = d.date.dt.quarter
    d["month"] = d.date.dt.month
    d["year_month"] = d.date.dt.strftime("%Y-%m")
    d["month_name_tr"] = d.month.map(MONTH_NAMES_TR)
    d["day"] = d.date.dt.day
    d["day_of_year"] = d.date.dt.dayofyear
    d["day_of_week"] = d.date.dt.dayofweek
    d["day_name_tr"] = d.day_of_week.map(DAY_NAMES_TR)
    d["iso_week"] = d.date.dt.isocalendar().week.astype(int)
    d["iso_year_week"] = d.date.dt.strftime("%G-W%V")
    d["is_weekend"] = d.day_of_week >= 5
    d["is_month_end"] = d.date.dt.is_month_end
    d["has_sales"] = d.date.isin(fact.sale_date.unique())

    # Takvim sabit sınırlardan kuruluyor; eksiksizliği doğrula.
    assert len(d) == 366, f"366 gün bekleniyordu (2024 artık yıl), {len(d)} üretildi"
    assert d.date.is_monotonic_increasing and d.date.is_unique, "Takvim kesintili veya tekrarlı"
    assert d.date.diff().dropna().eq(pd.Timedelta(days=1)).all(), "Takvimde gün atlaması var"
    # Fact'teki her satış günü takvimde karşılık bulmalı
    orphan_dates = set(fact.sale_date.unique()) - set(d.date)
    assert not orphan_dates, f"Takvimde olmayan satış günü: {sorted(orphan_dates)[:5]}"

    print(f"  {len(d)} gün ({d.date.min().date()} → {d.date.max().date()}), "
          f"satışsız gün: {int((~d.has_sales).sum())}")
    return d


def build_dim_store(fact: pd.DataFrame, dim_product: pd.DataFrame) -> pd.DataFrame:
    """Mağaza boyutu — TÜRETİLMİŞ özellikler. Coğrafi kolon kaynak veride yok."""
    print("\n-- dim_store --")

    s = fact.groupby("store_code").agg(
        net_sales=("amount", "sum"),
        gross_sales=("sales_amount", "sum"),
        return_amount=("return_amount", "sum"),
        net_quantity=("quantity", "sum"),
        n_transactions=("doc_id", "count"),
        active_months=("year_month", "nunique"),
        first_sale_date=("sale_date", "min"),
        last_sale_date=("sale_date", "max"),
    ).reset_index()

    s["return_rate_amount"] = np.where(s.gross_sales > 0,
                                       (s.return_amount.abs() / s.gross_sales).round(4), np.nan)
    s["avg_line_amount"] = (s.net_sales / s.n_transactions).round(2)

    s = s.sort_values("net_sales", ascending=False).reset_index(drop=True)
    s["revenue_rank"] = np.arange(1, len(s) + 1)
    s["revenue_share_pct"] = (s.net_sales / s.net_sales.sum() * 100).round(4)
    cum = s.revenue_share_pct.cumsum()
    # A/B/C dilimi kümülatif ciroya göre: ilk %50 → A, %50-80 → B, kalan → C
    s["revenue_tier"] = np.where(cum <= 50, "A", np.where(cum <= 80, "B", "C"))

    # Mağazanın baskın fiti
    fp = (fact.merge(dim_product[["product_code", "fit"]], on="product_code", how="left")
          .groupby(["store_code", "fit"]).amount.sum().reset_index())
    idx = fp.groupby("store_code").amount.idxmax()
    top = fp.loc[idx, ["store_code", "fit", "amount"]].rename(
        columns={"fit": "top_fit", "amount": "top_fit_net_sales"})
    s = s.merge(top, on="store_code", how="left")
    s["top_fit_share_pct"] = (s.top_fit_net_sales / s.net_sales * 100).round(2)
    s = s.drop(columns=["top_fit_net_sales"])

    order = ["store_code", "net_sales", "gross_sales", "return_amount", "return_rate_amount",
             "net_quantity", "n_transactions", "avg_line_amount", "revenue_rank",
             "revenue_share_pct", "revenue_tier", "active_months", "first_sale_date",
             "last_sale_date", "top_fit", "top_fit_share_pct"]
    s = s[order]

    assert s.store_code.is_unique, "dim_store.store_code unique değil"
    assert len(s) == fact.store_code.nunique(), "dim_store mağaza kaybetti"
    assert np.isclose(s.net_sales.sum(), fact.amount.sum()), "dim_store toplam kaybediyor"

    tiers = s.revenue_tier.value_counts().reindex(["A", "B", "C"]).fillna(0).astype(int)
    print(f"  {len(s)} mağaza | dilim A:{tiers.A} B:{tiers.B} C:{tiers.C} "
          f"| coğrafi kolon YOK, tüm özellikler türetilmiş")
    return s


# --------------------------------------------------------------------------
def main() -> None:
    cfg.header("05 — BI EXPORT (STAR SCHEMA)")
    cfg.ensure_dirs()

    # --- fact_sales ---
    print("\n-- fact_sales --")
    fact = pd.read_parquet(cfg.INTERIM / "fact_sales.parquet")
    unmapped = set(fact.columns) - set(FACT_RENAME)
    assert not unmapped, f"fact_sales'te eşlenmemiş kolon: {unmapped}"
    fact = fact.rename(columns=FACT_RENAME)[list(FACT_RENAME.values())]
    assert fact.doc_id.is_unique, "fact_sales.doc_id unique değil"
    print(f"  {len(fact):,} satır × {fact.shape[1]} kolon | net ciro {fact.amount.sum():,.2f} TL")

    # --- dim_product ---
    print("\n-- dim_product --")
    prod = pd.read_parquet(cfg.INTERIM / "dim_product.parquet")
    unmapped = set(prod.columns) - set(PRODUCT_RENAME)
    assert not unmapped, f"dim_product'ta eşlenmemiş kolon: {unmapped}"
    prod = prod.rename(columns=PRODUCT_RENAME)[list(PRODUCT_RENAME.values())]
    assert prod.product_code.is_unique, "dim_product.product_code unique değil"
    print(f"  {len(prod):,} ürün | {prod.fit.nunique()} normalize fit")

    dim_date = build_dim_date(fact)
    dim_store = build_dim_store(fact, prod)

    # --- Referans bütünlüğü: fact'teki her anahtar boyutta karşılık bulmalı ---
    print("\n-- Referans bütünlüğü --")
    checks = [
        ("fact.product_code → dim_product", set(fact.product_code) - set(prod.product_code)),
        ("fact.store_code   → dim_store", set(fact.store_code) - set(dim_store.store_code)),
        ("fact.sale_date    → dim_date", set(fact.sale_date) - set(dim_date.date)),
    ]
    for name, orphans in checks:
        print(f"  {name:<34} yetim anahtar: {len(orphans)}")
        assert not orphans, f"{name} referans bütünlüğü kırık: {list(orphans)[:5]}"

    # --- panel (modelleme girdisi) ---
    panel = pd.read_parquet(cfg.INTERIM / "panel_store_month.parquet")
    panel = panel.rename(columns=PANEL_RENAME)[list(PANEL_RENAME.values())]

    # --- Yazma ---
    print("\n-- data/processed/ --")
    frames = {"fact_sales": fact, "dim_product": prod, "dim_date": dim_date, "dim_store": dim_store}
    for name, df in frames.items():
        cfg.save_dataset(df, name, folder=cfg.PROCESSED, csv=True)
    cfg.save_dataset(panel, "panel_store_month", folder=cfg.PROCESSED, csv=True)

    # --- Veri sözlüğü ve özet ---
    cfg.save_table(to_dictionary_rows(frames), "05_data_dictionary")

    summary = pd.DataFrame(
        [(n, len(df), df.shape[1], "fact" if n.startswith("fact") else "dimension")
         for n, df in frames.items()]
        + [("panel_store_month", len(panel), panel.shape[1], "modelleme girdisi")],
        columns=["table", "n_rows", "n_columns", "role"])
    cfg.save_table(summary, "05_export_summary")
    print()
    print(summary.to_string(index=False))

    cfg.log_assumption(
        "BI katmanı ayrıştırıldı: 01-04 dahili çalışma dosyalarını data/interim/ altında orijinal "
        "kolon adlarıyla tutar, 05 ise data/processed/ altına snake_case star schema yazar. "
        "Aynı dosya adının iki farklı kolon şemasıyla yazılmasını engellemek için tek yazar kuralı."
    )
    cfg.log_assumption(
        f"`dim_date` veri aralığından değil SABİT sınırlardan kuruldu ({CALENDAR_START} → "
        f"{CALENDAR_END}, 366 gün) ve satışsız günleri de içerir; `has_sales` bayrağı ayrımı tutar."
    )

    print("\n05 tamamlandı. BI toolu artık data/processed/ altındaki 4 tabloyu okuyabilir.")


if __name__ == "__main__":
    main()
