"""Ortak yol sabitleri ve yardımcı fonksiyonlar.

Pipeline adımı değildir; 00-04 script'lerinin tekrar eden işlerini (klasör yolları,
figür kaydetme, tablo kaydetme, varsayım loglama) tek yerde toplar.
"""

from pathlib import Path

import pandas as pd

# --- Yol sabitleri ---
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"
NOTES = ROOT / "notes"

ASSUMPTIONS_FILE = NOTES / "assumptions.md"
ASSUMPTIONS_HEADER = "# Varsayımlar\n\nPipeline tarafından otomatik yazılır. Her satır bir karar.\n"

# Grafik standardı: tüm PNG'ler bu dpi ile kaydedilir (CLAUDE.md kuralı)
FIG_DPI = 150

# CLAUDE.md'de doğrulanmış satır sayıları — guard olarak kullanılır
EXPECTED_SALES_ROWS = 34_070
EXPECTED_PRODUCTS_ROWS = 1_511


def ensure_dirs() -> None:
    """Çıktı klasörlerini oluşturur (varsa dokunmaz)."""
    for d in (INTERIM, PROCESSED, FIGURES, TABLES, NOTES):
        d.mkdir(parents=True, exist_ok=True)


def save_fig(fig, name: str) -> Path:
    """Figürü outputs/figures/ altına dpi=150 ile kaydeder ve kapatır."""
    ensure_dirs()
    path = FIGURES / (name if name.endswith(".png") else f"{name}.png")
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight")
    print(f"  [figür] {path.relative_to(ROOT)}")
    import matplotlib.pyplot as plt

    plt.close(fig)
    return path


def save_table(df: pd.DataFrame, name: str, index: bool = False) -> Path:
    """Tabloyu outputs/tables/ altına CSV olarak kaydeder.

    Sunuma girecek her rakam bu fonksiyondan geçmek zorunda (CLAUDE.md kuralı).
    """
    ensure_dirs()
    path = TABLES / (name if name.endswith(".csv") else f"{name}.csv")
    df.to_csv(path, index=index, encoding="utf-8-sig")
    print(f"  [tablo] {path.relative_to(ROOT)}  ({len(df)} satır)")
    return path


def save_dataset(df: pd.DataFrame, name: str, folder: Path = PROCESSED, csv: bool = True) -> None:
    """Veri setini parquet (+ opsiyonel CSV) olarak kaydeder."""
    ensure_dirs()
    folder.mkdir(parents=True, exist_ok=True)
    df.to_parquet(folder / f"{name}.parquet", index=False)
    print(f"  [veri]  {(folder / f'{name}.parquet').relative_to(ROOT)}  ({len(df)} satır)")
    if csv:
        df.to_csv(folder / f"{name}.csv", index=False, encoding="utf-8-sig")


def log_assumption(text: str) -> None:
    """notes/assumptions.md'ye tek satırlık varsayım ekler.

    Idempotent: aynı satır ikinci kez yazılmaz, böylece pipeline tekrar
    çalıştırıldığında dosya şişmez.
    """
    ensure_dirs()
    line = f"- {text.strip()}"
    if not ASSUMPTIONS_FILE.exists():
        ASSUMPTIONS_FILE.write_text(ASSUMPTIONS_HEADER + "\n", encoding="utf-8")
    existing = ASSUMPTIONS_FILE.read_text(encoding="utf-8")
    if line in existing:
        return
    with ASSUMPTIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_raw_excel() -> Path:
    """data/raw/ altındaki tek xlsx dosyasını bulur.

    Dosya adı boşluk içerdiği için hardcode edilmiyor.
    """
    candidates = sorted(p for p in RAW.glob("*.xlsx") if not p.name.startswith("~$"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"data/raw/ altında tam olarak 1 xlsx bekleniyordu, {len(candidates)} bulundu: {candidates}"
        )
    return candidates[0]


def header(title: str) -> None:
    """Konsol çıktısı için başlık."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
