"""02 — Keşifçi veri analizi (EDA).

Betimsel profil: dağılımlar, aykırı değerler, iade oranı, mağaza konsantrasyonu,
fit dağılımı, beden dağılımı, saat bazlı yoğunluk.

Aykırı değer SİLİNMEZ; sadece tespit edilir, sayılır ve grafik ekseni kırpılır.
Satış ve iade asla aynı grafikte üst üste bindirilmez (CLAUDE.md kuralı).

Input : data/interim/fact_sales.parquet
        data/interim/dim_product.parquet
Output: outputs/tables/02_*.csv
        outputs/figures/02_*.png
        notes/findings.md
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as cfg

# Doğrulanmış renk paleti (dataviz validator: tüm checkler PASS, light mode)
C_SALES = "#2a78d6"   # satış / net — kategorik slot 1
C_RETURN = "#e34948"  # iade — kategorik slot 8
C_GRID = "#d8d8d4"
C_TEXT = "#52514e"
C_MUTED = "#b8b7b1"

_findings: list[str] = []


def finding(text: str) -> None:
    """Grafiğin altına tek cümlelik bulgu yorumu basar ve findings.md için saklar."""
    print(f"  → BULGU: {text}")
    _findings.append(text)


def style_axes(ax, xlabel: str = "", ylabel: str = "") -> None:
    """Recessive grid, üst/sağ spine yok."""
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(C_MUTED)
    ax.grid(axis="y", color=C_GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=C_TEXT, labelsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=C_TEXT)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=C_TEXT)


def tl(n: float) -> str:
    """Tutarı okunabilir TL kısaltmasına çevirir."""
    a = abs(n)
    if a >= 1e6:
        return f"{n / 1e6:,.1f}M TL"
    if a >= 1e3:
        return f"{n / 1e3:,.0f}K TL"
    return f"{n:,.0f} TL"


# --------------------------------------------------------------------------
def kpi_headline(f: pd.DataFrame) -> pd.DataFrame:
    """Sunumun kapak rakamları."""
    cfg.header("02 — KEŞİFÇİ VERİ ANALİZİ")
    print("\n-- Headline KPI --")

    gross = f.sales_amount.sum()
    ret = f.return_amount.sum()
    net = f.Amount.sum()
    gross_qty = int(f.sales_qty.sum())
    ret_qty = int(f.return_qty.sum())

    kpi = pd.DataFrame(
        [
            ("n_rows", len(f), "toplam satış satırı"),
            ("n_stores", f.StoreCode.nunique(), "farklı mağaza"),
            ("n_products", f.ProductCode.nunique(), "satışı olan ürün"),
            ("n_sizes", f.size_code.nunique(), "farklı beden kodu"),
            ("date_min", f.Date.min().date(), "ilk satış günü"),
            ("date_max", f.Date.max().date(), "son satış günü"),
            ("gross_sales_amount", round(gross, 2), "brüt satış tutarı (iade hariç)"),
            ("return_amount", round(ret, 2), "iade tutarı (negatif)"),
            ("net_sales_amount", round(net, 2), "net satış = brüt + iade"),
            ("gross_sales_qty", gross_qty, "brüt satış adedi"),
            ("return_qty", ret_qty, "iade adedi (negatif)"),
            ("net_qty", gross_qty + ret_qty, "net adet"),
            ("return_rate_amount", round(abs(ret) / gross, 4), "|iade tutarı| / brüt satış"),
            ("return_rate_qty", round(abs(ret_qty) / gross_qty, 4), "|iade adedi| / brüt adet"),
            ("avg_selling_price", round(gross / gross_qty, 2), "brüt ASP (iade hariç)"),
            ("n_anomaly_rows", int(f.is_anomaly.sum()), "ReturnFlag=0 ama Amount<0"),
        ],
        columns=["metric", "value", "description"],
    )
    for _, r in kpi.iterrows():
        print(f"  {r.metric:<22} {str(r.value):>16}   {r.description}")
    cfg.save_table(kpi, "02_kpi_headline")
    return kpi


# --------------------------------------------------------------------------
def distributions_and_outliers(f: pd.DataFrame) -> None:
    """Tutar / birim fiyat dağılımları + IQR ile aykırı değer tespiti."""
    print("\n-- Dağılımlar ve aykırı değerler --")

    sales = f[~f.is_return].copy()
    sales = sales[sales.Quantity > 0]
    sales["unit_price"] = sales.Amount / sales.Quantity

    # Sayısal profil
    prof = (
        f[["Quantity", "Amount", "DiscountAmount", "assumed_gross_amount"]]
        .describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99])
        .T.reset_index()
        .rename(columns={"index": "column"})
    )
    cfg.save_table(prof.round(2), "02_numeric_profile")

    # IQR aykırı değer tespiti (birim fiyat, sadece satış satırları)
    q1, q3 = sales.unit_price.quantile([0.25, 0.75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    is_out = (sales.unit_price < lo) | (sales.unit_price > hi)

    out_tbl = pd.DataFrame(
        [
            ("unit_price_q1", round(q1, 2)),
            ("unit_price_median", round(sales.unit_price.median(), 2)),
            ("unit_price_q3", round(q3, 2)),
            ("iqr", round(iqr, 2)),
            ("lower_fence", round(lo, 2)),
            ("upper_fence", round(hi, 2)),
            ("n_outlier_rows", int(is_out.sum())),
            ("outlier_pct_of_sales_rows", round(is_out.sum() / len(sales) * 100, 2)),
            ("outlier_amount_share_pct", round(sales[is_out].Amount.sum() / sales.Amount.sum() * 100, 2)),
            ("min_unit_price", round(sales.unit_price.min(), 2)),
            ("max_unit_price", round(sales.unit_price.max(), 2)),
        ],
        columns=["metric", "value"],
    )
    cfg.save_table(out_tbl, "02_outlier_profile")

    # Grafik: p1-p99 kırpılmış histogram + tam aralık boxplot
    p1, p99 = sales.unit_price.quantile([0.01, 0.99])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    axes[0].hist(sales.unit_price.clip(p1, p99), bins=60, color=C_SALES, edgecolor="white", linewidth=0.4)
    style_axes(axes[0], "Birim fiyat (TL)", "Satır sayısı")
    axes[0].set_title(f"Birim fiyat dağılımı\n(eksen p1–p99 aralığına kırpıldı: {p1:,.0f}–{p99:,.0f} TL)",
                      fontsize=10, color="#0b0b0b")

    bp = axes[1].boxplot(sales.unit_price, vert=False, widths=0.5, patch_artist=True,
                         flierprops=dict(marker="o", markersize=3, markerfacecolor=C_MUTED,
                                         markeredgecolor="none", alpha=0.35))
    bp["boxes"][0].set(facecolor=C_SALES, alpha=0.35, edgecolor=C_SALES, linewidth=2)
    for part in ("whiskers", "caps", "medians"):
        for line in bp[part]:
            line.set(color=C_SALES, linewidth=2)
    axes[1].axvline(hi, color=C_RETURN, linestyle="--", linewidth=1.5)
    axes[1].text(hi, 1.32, f" üst sınır {hi:,.0f} TL", color=C_RETURN, fontsize=8, va="center")
    style_axes(axes[1], "Birim fiyat (TL) — tam aralık", "")
    axes[1].set_yticks([])
    axes[1].grid(axis="x", color=C_GRID, linewidth=0.6)
    axes[1].set_title(f"Aykırı değerler (IQR 1.5×): {int(is_out.sum()):,} satır — silinmedi",
                      fontsize=10, color="#0b0b0b")

    fig.suptitle("Birim fiyat dağılımı ve aykırı değerler (yalnızca satış satırları)",
                 fontsize=12, color="#0b0b0b", y=1.02)
    cfg.save_fig(fig, "02_price_distribution")

    # Fiyat merdiveni: perakende fiyat noktaları ayrık, histogram bu yüzden dişli.
    ladder = sales.unit_price.round(2).value_counts()
    top8_share = ladder.head(8).sum() / len(sales) * 100
    n_negative = int((sales.unit_price < 0).sum())

    finding(
        f"Birim fiyat sürekli değil, ayrık bir fiyat merdiveninde toplanıyor: en sık 8 fiyat noktası "
        f"({ladder.index[0]:,.0f} TL başta olmak üzere) satış satırlarının %{top8_share:.0f}'ini kaplıyor, "
        f"medyan {sales.unit_price.median():,.0f} TL ve dağılım sola çarpık (skew {sales.unit_price.skew():.2f}); "
        f"IQR 1.5× kuralına göre {int(is_out.sum()):,} satır ({is_out.sum() / len(sales):.1%}) aykırı ama brüt cironun "
        f"yalnızca %{sales[is_out].Amount.sum() / sales.Amount.sum() * 100:.1f}'ini oluşturuyor — "
        f"negatif birim fiyatlı {n_negative} satırın tamamı ise zaten işaretlenmiş anomali kayıtları."
    )


# --------------------------------------------------------------------------
def return_analysis(f: pd.DataFrame) -> None:
    """İade oranı — tutar ve adet bazlı, satışla aynı grafikte değil."""
    print("\n-- İade analizi --")

    gross, ret = f.sales_amount.sum(), f.return_amount.sum()
    gross_qty, ret_qty = int(f.sales_qty.sum()), int(f.return_qty.sum())
    rr_amt, rr_qty = abs(ret) / gross, abs(ret_qty) / gross_qty

    tbl = pd.DataFrame(
        [
            ("Tutar (TL)", round(gross, 2), round(abs(ret), 2), round(gross + ret, 2), round(rr_amt, 4)),
            ("Adet", gross_qty, abs(ret_qty), gross_qty + ret_qty, round(rr_qty, 4)),
            ("Satır", int((~f.is_return).sum()), int(f.is_return.sum()), len(f),
             round(f.is_return.sum() / (~f.is_return).sum(), 4)),
        ],
        columns=["basis", "gross", "return", "net", "return_rate"],
    )
    cfg.save_table(tbl, "02_return_summary")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # Panel 1: brüt ve iade AYRI barlar (üst üste bindirme yok)
    axes[0].bar(["Brüt satış", "İade"], [gross, abs(ret)], color=[C_SALES, C_RETURN], width=0.5)
    for i, v in enumerate([gross, abs(ret)]):
        axes[0].text(i, v, f"\n{tl(v)}", ha="center", va="bottom", fontsize=10, color=C_TEXT)
    style_axes(axes[0], "", "Tutar (TL)")
    axes[0].set_ylim(0, gross * 1.18)
    axes[0].yaxis.set_major_formatter(lambda x, _: f"{x / 1e6:.0f}M")
    axes[0].set_title("Brüt satış ve iade tutarı", fontsize=10, color="#0b0b0b")

    # Panel 2: iki iade oranı tanımı yan yana
    axes[1].bar(["Tutar bazlı", "Adet bazlı"], [rr_amt * 100, rr_qty * 100],
                color=C_RETURN, width=0.5)
    for i, v in enumerate([rr_amt * 100, rr_qty * 100]):
        axes[1].text(i, v, f"\n%{v:.1f}", ha="center", va="bottom", fontsize=11, color=C_TEXT)
    style_axes(axes[1], "", "İade oranı (%)")
    axes[1].set_ylim(0, max(rr_amt, rr_qty) * 130)
    axes[1].set_title("İade oranı — iki tanım\n|iade| / brüt", fontsize=10, color="#0b0b0b")

    fig.suptitle("İade profili", fontsize=12, color="#0b0b0b", y=1.02)
    cfg.save_fig(fig, "02_return_profile")

    # Yorumun yönü veriden türetilir, elle yazılmaz.
    direction = (
        "tutar oranının adet oranından düşük kalması, iade edilenlerin ortalama olarak "
        "satılanlardan daha ucuz ürünler olduğunu gösteriyor"
        if rr_amt < rr_qty
        else "tutar oranının adet oranından yüksek olması, iade edilenlerin ortalama olarak "
             "satılanlardan daha pahalı ürünler olduğunu gösteriyor"
    )
    finding(
        f"İade oranı tutar bazlı %{rr_amt * 100:.1f}, adet bazlı %{rr_qty * 100:.1f} — "
        f"{f.is_return.sum():,} satır ({f.is_return.sum() / len(f):.0%}) iade kaydı ve "
        f"{direction}."
    )


# --------------------------------------------------------------------------
def store_concentration(f: pd.DataFrame) -> None:
    """Mağaza konsantrasyonu — top 20 ciro payı ve Pareto eğrisi."""
    print("\n-- Mağaza konsantrasyonu --")

    st = (
        f.groupby("StoreCode")
        .agg(net_sales=("Amount", "sum"), gross_sales=("sales_amount", "sum"),
             return_amount=("return_amount", "sum"), n_rows=("DocID", "count"),
             net_qty=("Quantity", "sum"))
        .sort_values("net_sales", ascending=False)
        .reset_index()
    )
    st["rank"] = np.arange(1, len(st) + 1)
    st["share_pct"] = st.net_sales / st.net_sales.sum() * 100
    st["cum_share_pct"] = st.share_pct.cumsum()
    st["return_rate_amount"] = (st.return_amount.abs() / st.gross_sales).round(4)
    cfg.save_table(st.round(2), "02_store_pareto")  # 350 mağazanın tamamı

    top20 = st.head(20)
    top20_share = top20.share_pct.sum()
    n_20pct = max(1, int(round(len(st) * 0.2)))
    share_of_top_20pct = st.head(n_20pct).share_pct.sum()
    n_for_half = int((st.cum_share_pct < 50).sum() + 1)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [1, 1]})

    axes[0].bar(top20.StoreCode.astype(str), top20.net_sales, color=C_SALES, width=0.68)
    style_axes(axes[0], "Mağaza kodu", "Net satış (TL)")
    axes[0].yaxis.set_major_formatter(lambda x, _: f"{x / 1e3:.0f}K")
    axes[0].tick_params(axis="x", rotation=45, labelsize=8)
    axes[0].set_title(f"En yüksek cirolu 20 mağaza — toplam net cironun %{top20_share:.1f}'i "
                      f"(350 mağazanın tamamı 02_store_pareto.csv'de)", fontsize=10, color="#0b0b0b")

    axes[1].plot(st["rank"], st.cum_share_pct, color=C_SALES, linewidth=2)
    axes[1].fill_between(st["rank"], st.cum_share_pct, color=C_SALES, alpha=0.10)
    axes[1].axvline(n_20pct, color=C_RETURN, linestyle="--", linewidth=1.5)
    axes[1].text(n_20pct + 4, 18, f"ilk %20 mağaza ({n_20pct})\n→ cironun %{share_of_top_20pct:.0f}'i",
                 color=C_RETURN, fontsize=9)
    axes[1].axhline(50, color=C_MUTED, linestyle=":", linewidth=1.2)
    axes[1].text(len(st) - 4, 52, f"cironun yarısı ilk {n_for_half} mağazada",
                 color=C_TEXT, fontsize=9, ha="right")
    style_axes(axes[1], "Mağaza sırası (ciroya göre, 1 = en yüksek)", "Kümülatif ciro payı (%)")
    axes[1].set_xlim(1, len(st))
    axes[1].set_ylim(0, 102)
    axes[1].set_title("Pareto eğrisi — 350 mağazanın tamamı", fontsize=10, color="#0b0b0b")

    fig.suptitle("Mağaza konsantrasyonu", fontsize=12, color="#0b0b0b", y=0.98)
    fig.tight_layout()
    cfg.save_fig(fig, "02_store_concentration")

    finding(
        f"350 mağazanın en iyi 20'si net cironun %{top20_share:.1f}'ini, ilk %20'lik dilim "
        f"({n_20pct} mağaza) %{share_of_top_20pct:.0f}'ini üretiyor ve cironun yarısı yalnızca "
        f"{n_for_half} mağazadan geliyor — ciro belirgin şekilde yoğunlaşmış, "
        f"mağaza bazlı tahminlemede bu az sayıda mağaza modelin doğruluğunu belirleyecek."
    )


# --------------------------------------------------------------------------
def fit_distribution(f: pd.DataFrame, dim_product: pd.DataFrame) -> None:
    """Fit (SubCategoryClass) dağılımı — betimsel; derin analiz 04'te."""
    print("\n-- Fit dağılımı --")

    m = f.merge(dim_product[["ProductCode", "fit"]], on="ProductCode", how="left", validate="many_to_one")
    fit = (
        m.groupby("fit")
        .agg(net_sales=("Amount", "sum"), gross_sales=("sales_amount", "sum"),
             return_amount=("return_amount", "sum"), n_rows=("DocID", "count"),
             net_qty=("Quantity", "sum"))
        .sort_values("net_sales", ascending=False)
        .reset_index()
    )
    fit["share_pct"] = (fit.net_sales / fit.net_sales.sum() * 100).round(2)
    fit["return_rate_amount"] = (fit.return_amount.abs() / fit.gross_sales).round(4)
    cfg.save_table(fit.round(2), "02_fit_distribution")

    # Toplam kaybı olmadığını doğrula
    assert np.isclose(fit.net_sales.sum(), f.Amount.sum()), "Fit kırılımı toplam kaybediyor"

    fig, ax = plt.subplots(figsize=(10, 5.5))
    d = fit.sort_values("net_sales")
    ax.barh(d.fit, d.net_sales, color=C_SALES, height=0.68)
    for y, (v, s) in enumerate(zip(d.net_sales, d.share_pct)):
        ax.text(v + fit.net_sales.max() * 0.012, y, f"{tl(v)}  (%{s:.1f})",
                va="center", fontsize=9, color=C_TEXT)
    style_axes(ax, "Net satış (TL)", "")
    ax.grid(axis="x", color=C_GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x / 1e6:.0f}M")
    ax.set_xlim(0, fit.net_sales.max() * 1.30)
    ax.set_title("Fit bazlı net satış dağılımı\n(tek anlamlı kategori kırılımı: SubCategoryClass)",
                 fontsize=11, color="#0b0b0b")
    cfg.save_fig(fig, "02_fit_distribution")

    top3 = fit.head(3)
    finding(
        f"{len(fit)} fit içinde ilk üçü ({', '.join(top3.fit)}) net cironun "
        f"%{top3.share_pct.sum():.0f}'ini taşıyor; en yüksek cirolu fit {fit.iloc[0].fit} "
        f"(%{fit.iloc[0].share_pct:.1f}) ve kuyrukta kalan fitler tek tek %5'in altında."
    )


# --------------------------------------------------------------------------
def size_distribution(f: pd.DataFrame) -> None:
    """Beden dağılımı — ProductItemCode'dan türetilen 71 beden kodu."""
    print("\n-- Beden dağılımı --")

    sz = (
        f.groupby("size_code")
        .agg(net_sales=("Amount", "sum"), net_qty=("Quantity", "sum"), n_rows=("DocID", "count"),
             gross_sales=("sales_amount", "sum"), return_amount=("return_amount", "sum"))
        .sort_values("net_qty", ascending=False)
        .reset_index()
    )
    sz["qty_share_pct"] = (sz.net_qty / sz.net_qty.sum() * 100).round(2)
    sz["return_rate_amount"] = (sz.return_amount.abs() / sz.gross_sales).round(4)
    cfg.save_table(sz.round(2), "02_size_distribution")  # 71 bedenin tamamı

    top = sz.head(20).sort_values("net_qty")
    top20_share = sz.head(20).qty_share_pct.sum()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top.size_code, top.net_qty, color=C_SALES, height=0.68)
    for y, v in enumerate(top.net_qty):
        ax.text(v + top.net_qty.max() * 0.012, y, f"{v:,}", va="center", fontsize=8.5, color=C_TEXT)
    style_axes(ax, "Net adet", "Beden kodu")
    ax.grid(axis="x", color=C_GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, top.net_qty.max() * 1.14)
    ax.set_title(f"En çok satan 20 beden kodu — {len(sz)} bedenin tamamı 02_size_distribution.csv'de\n"
                 f"(beden kodu ProductItemCode'dan türetildi)", fontsize=11, color="#0b0b0b")
    cfg.save_fig(fig, "02_size_distribution")

    n_thin = int((sz.net_qty < 10).sum())
    n_negative = int((sz.net_qty < 0).sum())
    finding(
        f"{len(sz)} farklı beden kodunun en çok satan 20'si net adedin %{top20_share:.0f}'ini kaplıyor "
        f"(en yoğun beden {sz.iloc[0].size_code}, {sz.iloc[0].net_qty:,} adet); kuyrukta {n_thin} beden "
        f"10 adedin altında kalıyor ve bunların {n_negative} tanesinin net adedi negatif — yani o bedenlerde "
        f"dönem içinde satılandan fazlası iade edilmiş, beden bazlı kalıp uyumu için doğrudan bir sinyal."
    )


# --------------------------------------------------------------------------
def hourly_density(f: pd.DataFrame) -> None:
    """Saat bazlı satış yoğunluğu."""
    print("\n-- Saat bazlı yoğunluk --")

    hr = (
        f.groupby("hour")
        .agg(net_sales=("Amount", "sum"), gross_sales=("sales_amount", "sum"),
             return_amount=("return_amount", "sum"), n_rows=("DocID", "count"),
             net_qty=("Quantity", "sum"))
        .reindex(range(f.hour.min(), f.hour.max() + 1), fill_value=0)
        .reset_index()
    )
    hr["share_pct"] = (hr.net_sales / hr.net_sales.sum() * 100).round(2)
    cfg.save_table(hr.round(2), "02_hourly")

    peak = hr.loc[hr.net_sales.idxmax()]
    top3 = hr.nlargest(3, "net_sales").sort_values("hour")

    fig, ax = plt.subplots(figsize=(11, 4.8))
    colors = [C_SALES if h in set(top3.hour) else "#9dbfe8" for h in hr.hour]
    ax.bar(hr.hour, hr.net_sales, color=colors, width=0.68)
    ax.text(peak.hour, peak.net_sales, f"\nzirve {int(peak.hour):02d}:00",
            ha="center", va="bottom", fontsize=9, color=C_TEXT)
    style_axes(ax, "Saat", "Net satış (TL)")
    ax.set_xticks(hr.hour)
    ax.set_xticklabels([f"{h:02d}" for h in hr.hour])
    ax.yaxis.set_major_formatter(lambda x, _: f"{x / 1e6:.1f}M")
    ax.set_ylim(0, hr.net_sales.max() * 1.16)
    ax.set_title(f"Saat bazlı net satış yoğunluğu (veri {f.hour.min():02d}:00–{f.hour.max():02d}:59 arası)",
                 fontsize=11, color="#0b0b0b")
    cfg.save_fig(fig, "02_hourly_density")

    finding(
        f"Satış günün {f.hour.min():02d}:00–{f.hour.max():02d}:59 aralığına sıkışmış; zirve saat "
        f"{int(peak.hour):02d}:00 (net cironun %{peak.share_pct:.1f}'i) ve en yoğun üç saat "
        f"({', '.join(f'{int(h):02d}:00' for h in top3.hour)}) tek başına "
        f"%{top3.share_pct.sum():.0f} pay tutuyor."
    )


# --------------------------------------------------------------------------
def data_quality_summary(f: pd.DataFrame) -> None:
    """Bayrak kolonlarının özeti — sunumun 1. başlığına kanıt."""
    print("\n-- Veri kalitesi özeti --")

    n = len(f)
    dq = pd.DataFrame(
        [
            ("is_return", int(f.is_return.sum()), "ReturnFlag=1, Quantity ve Amount negatif"),
            ("is_anomaly", int(f.is_anomaly.sum()), "ReturnFlag=0 ama Amount<0 — işaretlendi, silinmedi"),
            ("discount_gt_amount", int(f.discount_gt_amount.sum()), "satış satırında DiscountAmount > Amount"),
            ("discount_negative", int(f.discount_negative.sum()), "negatif iskonto (tamamı iade satırı)"),
            ("ChangeCardFlag=1", int((f.ChangeCardFlag == 1).sum()), "semantiği doğrulanmadı, analiz edilmedi"),
            ("null_any_column", int(f.isna().sum().sum()), "fact_sales'te toplam null"),
        ],
        columns=["flag", "n_rows", "description"],
    )
    dq["pct_of_rows"] = (dq.n_rows / n * 100).round(2)
    for _, r in dq.iterrows():
        print(f"  {r.flag:<22} {r.n_rows:>8,}  (%{r.pct_of_rows:.2f})  {r.description}")
    cfg.save_table(dq, "02_dataquality_summary")


# --------------------------------------------------------------------------
def write_findings() -> None:
    """Bulguları notes/findings.md'ye yazar (idempotent — dosya baştan yazılır)."""
    lines = ["# Bulgular — 02 EDA", "",
             "Pipeline tarafından otomatik üretildi. Her satır bir grafiğin tek cümlelik yorumu.", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(_findings, 1)]
    (cfg.NOTES / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  [not]   notes/findings.md ({len(_findings)} bulgu)")


def main() -> None:
    cfg.ensure_dirs()
    f = pd.read_parquet(cfg.INTERIM / "fact_sales.parquet")
    dim_product = pd.read_parquet(cfg.INTERIM / "dim_product.parquet")

    kpi_headline(f)
    distributions_and_outliers(f)
    return_analysis(f)
    store_concentration(f)
    fit_distribution(f, dim_product)
    size_distribution(f)
    hourly_density(f)
    data_quality_summary(f)
    write_findings()

    print("\n02 tamamlandı.")


if __name__ == "__main__":
    main()
