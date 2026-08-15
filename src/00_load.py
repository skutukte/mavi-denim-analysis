"""00 — Ham veri okuma. Hiçbir temizlik yapmaz.

Excel'i bir kez okur, olduğu gibi parquet'e alır. Date serial int olarak,
Time int olarak, TR/EN etiketler ham haliyle kalır. Tüm dönüşümler 01_clean.py'de.

Input : data/raw/*.xlsx  (Sales + Products sheet'leri)
Output: data/interim/sales_raw.parquet
        data/interim/products_raw.parquet
        outputs/tables/00_schema_profile.csv
"""

import pandas as pd

import config as cfg


def profile_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Her kolon için dtype / null / unique / örnek değer profili çıkarır."""
    rows = []
    for col in df.columns:
        s = df[col]
        samples = s.dropna().unique()[:3]
        rows.append(
            {
                "source": source,
                "column": col,
                "dtype": str(s.dtype),
                "n_rows": len(s),
                "n_null": int(s.isna().sum()),
                "n_unique": int(s.nunique(dropna=True)),
                "sample_values": " | ".join(str(v) for v in samples),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    cfg.header("00 — HAM VERİ OKUMA")
    cfg.ensure_dirs()

    src = cfg.find_raw_excel()
    print(f"Kaynak dosya: {src.name}")

    sales = pd.read_excel(src, sheet_name="Sales")
    products = pd.read_excel(src, sheet_name="Products")

    print(f"Sales    : {sales.shape[0]:,} satır × {sales.shape[1]} kolon")
    print(f"Products : {products.shape[0]:,} satır × {products.shape[1]} kolon")

    # Guard: beklenmedik satır sayısı = yanlış dosya. Sessizce devam etme.
    assert len(sales) == cfg.EXPECTED_SALES_ROWS, (
        f"Sales satır sayısı beklenenden farklı: {len(sales)} != {cfg.EXPECTED_SALES_ROWS}"
    )
    assert len(products) == cfg.EXPECTED_PRODUCTS_ROWS, (
        f"Products satır sayısı beklenenden farklı: {len(products)} != {cfg.EXPECTED_PRODUCTS_ROWS}"
    )
    assert products["ProductCode"].is_unique, "Products.ProductCode unique değil"
    assert sales["DocID"].is_unique, "Sales.DocID unique değil"

    cfg.save_dataset(sales, "sales_raw", folder=cfg.INTERIM, csv=False)
    cfg.save_dataset(products, "products_raw", folder=cfg.INTERIM, csv=False)

    profile = pd.concat(
        [profile_frame(sales, "Sales"), profile_frame(products, "Products")],
        ignore_index=True,
    )
    cfg.save_table(profile, "00_schema_profile")

    print("\n00 tamamlandı.")


if __name__ == "__main__":
    main()
