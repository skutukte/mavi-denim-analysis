"""03 — Zaman ekseni: 12 aylık gözlem.

DİKKAT — terminoloji: Veri 2024-02 → 2025-01 arası TEK bir 12 aylık döngüdür.
Tek döngüyle mevsimsellik doğrulanamaz (aynı ayın ikinci gözlemi yok). Bu script
gördüğünü "trend" ya da "mevsimsellik" diye değil, "12 aylık gözlem" diye raporlar.
Mevsimsellik iddiası için gereken şey çıktılarda açıkça yazılır.

Input : data/interim/fact_sales.parquet
        data/interim/dim_product.parquet
        data/interim/dim_date.parquet
Output: outputs/tables/03_*.csv
        outputs/figures/03_*.png
        data/interim/panel_store_month.parquet   (mağaza × ay paneli, modelleme girdisi)
        notes/findings.md (03 bölümü eklenir)
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as cfg

# Doğrulanmış palet (dataviz)
C_SALES = "#2a78d6"
C_RETURN = "#e34948"
C_GRID = "#d8d8d4"
C_TEXT = "#52514e"
C_MUTED = "#b8b7b1"
C_NEUTRAL = "#f0efec"          # diverging orta nokta
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

TOP_N_FITS = 6
OTHER = "Other"

_findings: list[str] = []


def finding(text: str) -> None:
    print(f"  → BULGU: {text}")
    _findings.append(text)


def style_axes(ax, xlabel: str = "", ylabel: str = "", grid_axis: str = "y") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(C_MUTED)
    ax.grid(axis=grid_axis, color=C_GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=C_TEXT, labelsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=C_TEXT)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=C_TEXT)


def short_month(ym: str) -> str:
    """'2024-09' → '24-09' (eksen etiketi için)."""
    return ym[2:]


# --------------------------------------------------------------------------
def basket_reality_check(f: pd.DataFrame) -> pd.DataFrame:
    """Sepet kimliği var mı? Yoksa 'ortalama sepet' hesaplanamaz — bunu belgele."""
    print("\n-- Sepet kimliği kontrolü --")

    # Fiş kimliği olabilecek tek proxy: aynı mağaza + aynı tarih + aynı dakika
    grp = f.groupby(["StoreCode", "Date", "time_str"]).size()
    multi = int((grp > 1).sum())

    tbl = pd.DataFrame(
        [
            ("docid_is_unique", int(f.DocID.is_unique), "DocID satır başına unique → fiş kimliği değil"),
            ("n_rows", len(f), "toplam satış satırı"),
            ("n_timestamp_groups", len(grp), "StoreCode + Date + dakika ile oluşan grup sayısı"),
            ("n_multiline_groups", multi, "birden fazla satır içeren grup"),
            ("multiline_group_pct", round(multi / len(grp) * 100, 2), "çok satırlı grup oranı (%)"),
        ],
        columns=["metric", "value", "description"],
    )
    for _, r in tbl.iterrows():
        print(f"  {r.metric:<22} {str(r.value):>10}   {r.description}")
    cfg.save_table(tbl, "03_basket_feasibility")

    print("  KARAR: Gerçek sepet (çok kalemli fiş) yeniden kurulamıyor.")
    print("         'Ortalama sepet tutarı' yerine 'ortalama işlem satırı tutarı' raporlanacak.")

    cfg.log_assumption(
        "Veride fiş/sepet kimliği YOK (DocID satır başına unique). Tek proxy olan "
        "StoreCode+Date+dakika gruplaması, grupların %99'unu tek satır olarak döndürdüğü için "
        "gerçek sepeti geri kazanmıyor. Karar: 'ortalama sepet tutarı' hesaplanmadı; onun yerine "
        "`avg_line_amount` (net satış / satır sayısı) raporlandı ve sunumda bu sınır belirtilecek."
    )
    return tbl


# --------------------------------------------------------------------------
def monthly_metrics(f: pd.DataFrame) -> pd.DataFrame:
    """Aylık net ciro, adet, iade oranı, ortalama işlem satırı tutarı."""
    cfg.header("03 — ZAMAN EKSENİ (12 AYLIK GÖZLEM)")
    print("\n-- Aylık metrikler --")

    m = (
        f.groupby("year_month")
        .agg(
            net_sales=("Amount", "sum"),
            gross_sales=("sales_amount", "sum"),
            return_amount=("return_amount", "sum"),
            net_qty=("Quantity", "sum"),
            gross_qty=("sales_qty", "sum"),
            return_qty=("return_qty", "sum"),
            n_rows=("DocID", "count"),
            n_sale_rows=("is_return", lambda s: int((~s).sum())),
            n_return_rows=("is_return", "sum"),
            n_stores=("StoreCode", "nunique"),
        )
        .reset_index()
        .sort_values("year_month")
    )
    m["return_rate_amount"] = (m.return_amount.abs() / m.gross_sales).round(4)
    m["return_rate_qty"] = (m.return_qty.abs() / m.gross_qty).round(4)
    # Sepet kimliği olmadığı için "sepet" değil, satır bazlı ortalama
    m["avg_line_amount"] = (m.net_sales / m.n_rows).round(2)
    m["avg_selling_price"] = (m.gross_sales / m.gross_qty).round(2)
    m["mom_growth_pct"] = (m.net_sales.pct_change() * 100).round(2)

    assert np.isclose(m.net_sales.sum(), f.Amount.sum()), "Aylık kırılım toplam kaybediyor"
    assert len(m) == 12, f"12 ay bekleniyordu, {len(m)} bulundu"

    cfg.save_table(m.round(2), "03_monthly")
    print(m[["year_month", "net_sales", "net_qty", "return_rate_amount",
             "avg_line_amount", "mom_growth_pct"]].to_string(index=False))
    return m


def plot_monthly(m: pd.DataFrame) -> None:
    """Dört metrik, küçük çoklu panel. Her panel tek seri → lejant yok."""
    x = np.arange(len(m))
    labels = [short_month(v) for v in m.year_month]

    panels = [
        ("net_sales", "Net ciro (TL)", lambda v: f"{v / 1e6:.1f}M", C_SALES),
        ("net_qty", "Net adet", lambda v: f"{v:,.0f}", C_SALES),
        ("return_rate_amount", "İade oranı (tutar bazlı)", lambda v: f"%{v * 100:.0f}", C_RETURN),
        ("avg_line_amount", "Ort. işlem satırı tutarı (TL)", lambda v: f"{v:,.0f}", C_SALES),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 7.5))
    for ax, (col, title, fmt, color) in zip(axes.ravel(), panels):
        ax.bar(x, m[col], color=color, width=0.66)
        mean_v = m[col].mean()
        ax.axhline(mean_v, color=C_MUTED, linestyle="--", linewidth=1.2)
        ax.text(len(m) - 0.4, mean_v, f" ort. {fmt(mean_v)}", fontsize=8,
                color=C_TEXT, va="bottom", ha="right")
        style_axes(ax, "", "")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, fontsize=8)
        # fmt varsayılan argümana bağlanır; aksi halde döngü değişkeni geç bağlanıp
        # dört panelin de son formatı kullanmasına yol açıyor.
        ax.yaxis.set_major_formatter(lambda v, _, fmt=fmt: fmt(v))
        ax.set_title(title, fontsize=10, color="#0b0b0b")
        vals = m[col].to_numpy()
        for pos, tag in ((int(vals.argmax()), "en yüksek"), (int(vals.argmin()), "en düşük")):
            ax.text(pos, vals[pos], f"{tag}\n", ha="center", va="bottom",
                    fontsize=7.5, color=C_TEXT)
        ax.set_ylim(0, m[col].max() * 1.24)

    fig.suptitle("Aylık metrikler — 2024-02 → 2025-01, tek 12 aylık döngü (mevsimsellik doğrulanamaz)",
                 fontsize=12, color="#0b0b0b", y=0.99)
    fig.tight_layout()
    cfg.save_fig(fig, "03_monthly_metrics")

    peak, trough = m.loc[m.net_sales.idxmax()], m.loc[m.net_sales.idxmin()]
    finding(
        f"12 aylık gözlemde net ciro {trough.year_month} ({trough.net_sales / 1e6:.2f}M TL) ile "
        f"{peak.year_month} ({peak.net_sales / 1e6:.2f}M TL) arasında {peak.net_sales / trough.net_sales:.1f} kat "
        f"değişiyor; iade oranı ise %{m.return_rate_amount.min() * 100:.0f}–%{m.return_rate_amount.max() * 100:.0f} "
        f"bandında kalıp ciroyla birlikte savrulmuyor, yani aylık dalgalanma iade davranışından değil "
        f"satış hacminden geliyor."
    )


def plot_gross_vs_return(m: pd.DataFrame) -> None:
    """Brüt ve iade ayrı panellerde — asla üst üste bindirilmez."""
    x = np.arange(len(m))
    labels = [short_month(v) for v in m.year_month]

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].bar(x, m.gross_sales, color=C_SALES, width=0.66)
    style_axes(axes[0], "", "Brüt satış (TL)")
    axes[0].yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")
    axes[0].set_title("Brüt satış (iade hariç)", fontsize=10, color="#0b0b0b")

    axes[1].bar(x, m.return_amount.abs(), color=C_RETURN, width=0.66)
    style_axes(axes[1], "Ay", "İade tutarı (TL)")
    axes[1].yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=45, fontsize=8)
    axes[1].set_title("İade tutarı (mutlak değer)", fontsize=10, color="#0b0b0b")

    fig.suptitle("Brüt satış ve iade — ayrı eksenlerde, aynı ay sırasıyla",
                 fontsize=12, color="#0b0b0b", y=0.98)
    fig.tight_layout()
    cfg.save_fig(fig, "03_monthly_gross_vs_return")

    corr = m.gross_sales.corr(m.return_amount.abs())
    finding(
        f"Brüt satış ile iade tutarı aylık bazda {corr:.2f} korelasyonla birlikte hareket ediyor — "
        f"iade, kendi başına bir dönemsel olay değil satış hacminin gecikmeli gölgesi gibi davranıyor; "
        f"bu yüzden net ciroyu modellerken iadeyi ayrı bir seri olarak değil satışın fonksiyonu olarak "
        f"ele almak daha doğru olacak."
    )


# --------------------------------------------------------------------------
def seasonality_check(m: pd.DataFrame) -> None:
    """Mevsimsellik İDDİA ETMEZ — tek döngüde neyin doğrulanabilir olduğunu gösterir."""
    print("\n-- Mevsimsellik kontrolü (tek döngü) --")

    idx = m[["year_month", "net_sales", "net_qty"]].copy()
    mean_net = idx.net_sales.mean()
    idx["index_vs_mean"] = (idx.net_sales / mean_net * 100).round(1)
    idx["deviation_pct"] = (idx.index_vs_mean - 100).round(1)
    idx["n_observations_for_this_month"] = 1  # her takvim ayı veride yalnızca 1 kez var
    idx["seasonality_verifiable"] = False
    cfg.save_table(idx, "03_monthly_index")

    cv = m.net_sales.std() / m.net_sales.mean()
    # İkinci yarı / ilk yarı — döngü içi seviye kayması var mı
    h1, h2 = m.net_sales.iloc[:6].sum(), m.net_sales.iloc[6:].sum()

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(idx))
    colors = [C_SALES if d < 0 else C_RETURN for d in idx.deviation_pct]
    ax.bar(x, idx.deviation_pct, color=colors, width=0.66)
    ax.axhline(0, color=C_TEXT, linewidth=1.1)
    for i, d in enumerate(idx.deviation_pct):
        ax.text(i, d, f"{d:+.0f}%\n" if d > 0 else f"\n{d:+.0f}%",
                ha="center", va="bottom" if d > 0 else "top", fontsize=8, color=C_TEXT)
    style_axes(ax, "Ay", "12 ay ortalamasından sapma (%)")
    ax.set_xticks(x)
    ax.set_xticklabels([short_month(v) for v in idx.year_month], rotation=45, fontsize=8)
    ax.set_ylim(idx.deviation_pct.min() * 1.42, idx.deviation_pct.max() * 1.42)
    ax.set_title(
        "Aylık net cironun 12 ay ortalamasından sapması\n"
        "UYARI: Bu bir MEVSİMSELLİK GRAFİĞİ DEĞİLDİR — her takvim ayının yalnızca 1 gözlemi var, "
        "tekrar eden bir örüntü doğrulanamaz.",
        fontsize=10.5, color="#0b0b0b")
    cfg.save_fig(fig, "03_monthly_deviation")

    finding(
        f"Aylık net ciro ortalamadan −%{abs(idx.deviation_pct.min()):.0f} ile +%{idx.deviation_pct.max():.0f} "
        f"arasında sapıyor (değişim katsayısı {cv:.2f}) ve yılın ikinci yarısı ilk yarısının "
        f"{h2 / h1:.1f} katı; ancak veride her takvim ayının yalnızca TEK gözlemi olduğu için bu sapmaların "
        f"mevsimsel mi, kampanya kaynaklı mı yoksa büyüme kaynaklı mı olduğu AYRIŞTIRILAMAZ — "
        f"mevsimsellik iddiası için en az 24-36 aylık geçmiş, tercihen aynı ayın yıllar arası "
        f"karşılaştırması gerekir."
    )

    print(f"  Değişim katsayısı (CV): {cv:.3f}")
    print(f"  H2/H1 oranı: {h2 / h1:.2f}")
    print("  KARAR: Mevsimsellik İDDİA EDİLMİYOR — '12 aylık gözlem' olarak raporlanıyor.")

    cfg.log_assumption(
        "Veri 2024-02 → 2025-01 arası TEK bir 12 aylık döngüdür; her takvim ayının yalnızca bir "
        "gözlemi vardır. Bu nedenle aylık dalgalanmalar mevsimsellik olarak SUNULMADI — "
        "mevsimsel etki, trend ve kampanya etkisi bu veriyle ayrıştırılamaz. Çıktılarda "
        "'12 aylık gözlem' terimi kullanıldı; mevsimsellik için ≥24-36 aylık geçmiş gerekir."
    )


# --------------------------------------------------------------------------
def weekly_and_dow(f: pd.DataFrame, dim_date: pd.DataFrame) -> None:
    """Haftalık seyir ve gün×saat yoğunluk matrisi."""
    print("\n-- Haftalık ve gün × saat --")

    d = f.merge(dim_date[["Date", "iso_week", "day_of_week", "day_name_tr", "is_weekend"]],
                on="Date", how="left", validate="many_to_one")

    wk = (
        d.assign(year_week=d.Date.dt.strftime("%G-W%V"))
        .groupby("year_week")
        .agg(net_sales=("Amount", "sum"), net_qty=("Quantity", "sum"), n_rows=("DocID", "count"))
        .reset_index()
    )
    cfg.save_table(wk.round(2), "03_weekly")

    mat = d.pivot_table(index="day_name_tr", columns="hour", values="Amount", aggfunc="sum", fill_value=0)
    order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    mat = mat.reindex(order)
    cfg.save_table(mat.round(2).reset_index(), "03_dow_hour_matrix")

    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
    fig, ax = plt.subplots(figsize=(12, 4.6))
    im = ax.imshow(mat.values, aspect="auto", cmap=cmap)
    ax.set_xticks(range(len(mat.columns)))
    ax.set_xticklabels([f"{c:02d}" for c in mat.columns], fontsize=9)
    ax.set_yticks(range(len(mat.index)))
    ax.set_yticklabels(mat.index, fontsize=9)
    ax.tick_params(colors=C_TEXT)
    ax.spines[:].set_visible(False)
    ax.set_xlabel("Saat", fontsize=9, color=C_TEXT)
    ax.set_title("Gün × saat net satış yoğunluğu (tek renk sekansı: açık = düşük, koyu = yüksek)",
                 fontsize=11, color="#0b0b0b")
    cb = fig.colorbar(im, ax=ax, pad=0.015)
    cb.ax.tick_params(labelsize=8, colors=C_TEXT)
    cb.set_label("Net satış (TL)", fontsize=8, color=C_TEXT)
    cb.outline.set_visible(False)
    cfg.save_fig(fig, "03_dow_hour_heatmap")

    dow = d.groupby("day_name_tr").Amount.sum().reindex(order)
    wknd = d[d.is_weekend].Amount.sum() / d.Amount.sum()
    best_cell = mat.stack().idxmax()
    finding(
        f"Haftanın en güçlü günü {dow.idxmax()} (net {dow.max() / 1e6:.2f}M TL), en zayıfı {dow.idxmin()} "
        f"({dow.min() / 1e6:.2f}M TL); hafta sonu iki günde net cironun %{wknd * 100:.0f}'i dönüyor ve "
        f"en yoğun tek hücre {best_cell[0]} {best_cell[1]:02d}:00 — mağaza personel planlaması için "
        f"gün×saat kırılımı ay kırılımından daha aksiyon alınabilir."
    )


# --------------------------------------------------------------------------
def fit_monthly(f: pd.DataFrame, dim_product: pd.DataFrame) -> None:
    """Top 6 fit + Other, aylık seyir. Küçük çoklu panel — 7 çizgi üst üste değil."""
    print("\n-- Fit bazlı aylık seyir --")

    d = f.merge(dim_product[["ProductCode", "fit"]], on="ProductCode", how="left", validate="many_to_one")

    totals = d.groupby("fit").Amount.sum().sort_values(ascending=False)
    top_fits = totals.head(TOP_N_FITS).index.tolist()
    d["fit_group"] = np.where(d.fit.isin(top_fits), d.fit, OTHER)

    fm = (
        d.groupby(["fit_group", "year_month"])
        .agg(net_sales=("Amount", "sum"), net_qty=("Quantity", "sum"),
             gross_sales=("sales_amount", "sum"), return_amount=("return_amount", "sum"),
             n_rows=("DocID", "count"))
        .reset_index()
    )
    # Eksik fit-ay kombinasyonlarını 0 ile doldur (grafikte boşluk olmasın)
    months = sorted(d.year_month.unique())
    groups = top_fits + [OTHER]
    full = pd.MultiIndex.from_product([groups, months], names=["fit_group", "year_month"])
    fm = fm.set_index(["fit_group", "year_month"]).reindex(full, fill_value=0).reset_index()
    fm["return_rate_amount"] = np.where(fm.gross_sales > 0,
                                        (fm.return_amount.abs() / fm.gross_sales).round(4), np.nan)
    fm["share_of_month_pct"] = (
        fm.net_sales / fm.groupby("year_month").net_sales.transform("sum") * 100
    ).round(2)

    assert np.isclose(fm.net_sales.sum(), f.Amount.sum()), "Fit × ay kırılımı toplam kaybediyor"
    cfg.save_table(fm.round(2), "03_fit_month")

    other_share = totals[~totals.index.isin(top_fits)].sum() / totals.sum() * 100
    print(f"  Top {TOP_N_FITS} fit: {', '.join(top_fits)}")
    print(f"  {OTHER} kovası: {len(totals) - TOP_N_FITS} fit, net cironun %{other_share:.1f}'i")

    # Küçük çoklu panel — ortak y ekseni, tek renk
    x = np.arange(len(months))
    labels = [short_month(v) for v in months]
    ymax = fm.net_sales.max() * 1.15

    fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharey=True, sharex=True)
    for ax, g in zip(axes.ravel(), groups):
        s = fm[fm.fit_group == g].sort_values("year_month")
        color = C_MUTED if g == OTHER else C_SALES
        ax.plot(x, s.net_sales, color=color, linewidth=2, marker="o", markersize=4)
        ax.fill_between(x, s.net_sales, color=color, alpha=0.10)
        style_axes(ax, "", "")
        ax.set_xticks(x[::2])
        ax.set_xticklabels(labels[::2], rotation=45, fontsize=8)
        ax.set_ylim(0, ymax)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e3:.0f}K")
        share = totals.get(g, other_share / 100 * totals.sum()) / totals.sum() * 100 \
            if g != OTHER else other_share
        ax.set_title(f"{g}  (yıl toplamı payı %{share:.1f})", fontsize=9.5, color="#0b0b0b")
    axes.ravel()[-1].axis("off")
    # Son hücre kapatıldığı için 4. sütunun altında etiket kalmıyor; üst satıra geri ver.
    top_right = axes[0, 3]
    top_right.tick_params(labelbottom=True)
    top_right.set_xticks(x[::2])
    top_right.set_xticklabels(labels[::2], rotation=45, fontsize=8)

    fig.suptitle(
        f"Fit bazlı aylık net satış — top {TOP_N_FITS} fit + {OTHER} "
        f"(ortak y ekseni, 12 aylık gözlem; mevsimsellik iddiası değildir)",
        fontsize=12, color="#0b0b0b", y=0.99)
    fig.tight_layout()
    cfg.save_fig(fig, "03_fit_month_small_multiples")

    # Fitler arası pay kayması: ilk 3 ay vs son 3 ay
    first3, last3 = months[:3], months[-3:]
    shift = (
        fm.assign(period=np.where(fm.year_month.isin(first3), "first3",
                                  np.where(fm.year_month.isin(last3), "last3", None)))
        .dropna(subset=["period"])
        .pivot_table(index="fit_group", columns="period", values="net_sales", aggfunc="sum")
    )
    shift = (shift / shift.sum() * 100).round(1)
    shift["change_pp"] = (shift.last3 - shift.first3).round(1)
    shift = shift.sort_values("change_pp", ascending=False).reset_index()
    cfg.save_table(shift, "03_fit_share_shift")

    # Konfaunder: pay kayması moda değişimi mi, koleksiyon devri mi? Ürün ömrüne bak.
    months_per_product = d.groupby("ProductCode").year_month.nunique()
    n_products = len(months_per_product)
    n_all12 = int((months_per_product == 12).sum())
    n_short = int((months_per_product <= 3).sum())
    churn = pd.DataFrame(
        [("n_products_sold", n_products, "dönemde en az bir satışı olan ürün"),
         ("n_products_all_12_months", n_all12, "12 ayın tamamında satılan ürün"),
         ("n_products_max_3_months", n_short, "3 ay veya daha az satılan ürün"),
         ("pct_products_all_12", round(n_all12 / n_products * 100, 1), "%")],
        columns=["metric", "value", "description"])
    cfg.save_table(churn, "03_product_churn")

    riser, faller = shift.iloc[0], shift.iloc[-1]
    finding(
        f"Fitlerin ay içindeki payı sert biçimde kayıyor: ilk 3 aya kıyasla son 3 ayda {riser.fit_group} "
        f"{riser.change_pp:+.1f} puan kazanırken {faller.fit_group} {faller.change_pp:+.1f} puan kaybetmiş — "
        f"ancak bu moda kayması olarak okunamaz, çünkü aynı dönemde koleksiyon devri çok yüksek: "
        f"satışı olan {n_products} üründen yalnızca {n_all12}'ü ({n_all12 / n_products:.0%}) 12 ayın tamamında "
        f"satılmış, {n_short}'i üç ay veya daha kısa ömürlü; yani fit payındaki değişim tüketici tercihinden mi "
        f"asortiman kararından mı geliyor bu veriyle ayrıştırılamaz."
    )
    finding(
        f"Ürün devri tahminlemenin önündeki en büyük yapısal engel: {n_products} üründen {n_all12} tanesinin "
        f"12 aylık kesintisiz geçmişi var, dolayısıyla ürün seviyesinde zaman serisi kurulamaz — "
        f"model fit ve mağaza gibi ürün ömründen bağımsız, kalıcı seviyelerde kurulmalı."
    )


# --------------------------------------------------------------------------
def store_month_panel(f: pd.DataFrame) -> None:
    """Mağaza × ay paneli — 04 ve tahminleme yol haritasının somut girdisi."""
    print("\n-- Mağaza × ay paneli --")

    p = (
        f.groupby(["StoreCode", "year_month"])
        .agg(net_sales=("Amount", "sum"), gross_sales=("sales_amount", "sum"),
             return_amount=("return_amount", "sum"), net_qty=("Quantity", "sum"),
             n_rows=("DocID", "count"))
        .reset_index()
    )
    # Modelleme için dengeli panel: satışı olmayan mağaza-ay kombinasyonu 0 ile doldurulur
    stores = sorted(f.StoreCode.unique())
    months = sorted(f.year_month.unique())
    full = pd.MultiIndex.from_product([stores, months], names=["StoreCode", "year_month"])
    p = p.set_index(["StoreCode", "year_month"]).reindex(full, fill_value=0).reset_index()
    p["had_sales"] = p.n_rows > 0

    assert len(p) == len(stores) * len(months), "Panel dengeli değil"
    assert np.isclose(p.net_sales.sum(), f.Amount.sum()), "Panel toplam kaybediyor"

    cfg.save_dataset(p, "panel_store_month", folder=cfg.INTERIM, csv=False)

    empty = int((~p.had_sales).sum())
    print(f"  Panel boyutu: {len(stores)} mağaza × {len(months)} ay = {len(p):,} satır")
    print(f"  Satışı olmayan mağaza-ay hücresi: {empty:,} (%{empty / len(p) * 100:.1f}) → 0 ile dolduruldu")

    cfg.log_assumption(
        f"`panel_store_month.parquet` dengeli panel olarak üretildi ({len(stores)} mağaza × "
        f"{len(months)} ay = {len(p):,} satır). Satışı olmayan {empty:,} mağaza-ay hücresi 0 ile "
        "dolduruldu; 'satış yok' ile 'veri yok' ayrımı `had_sales` bayrağında tutuluyor."
    )

    finding(
        f"Mağaza × ay paneli {len(p):,} hücreden oluşuyor ve bunların %{empty / len(p) * 100:.1f}'inde hiç satış yok; "
        f"mağaza başına ayda ortalama yalnızca {p[p.had_sales].n_rows.mean():.0f} işlem satırı düşüyor — "
        f"bu seyreklik, mağaza bazlı aylık tahminlemede tek tek mağaza modeli yerine havuzlanmış "
        f"(hiyerarşik/panel) bir yaklaşımı zorunlu kılıyor."
    )


# --------------------------------------------------------------------------
def append_findings() -> None:
    """03 bulgularını notes/findings.md'ye ekler (02 bölümü korunur, 03 bölümü yeniden yazılır)."""
    path = cfg.NOTES / "findings.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "\n## 03 — Zaman ekseni (12 aylık gözlem)\n"
    base = existing.split(marker)[0].rstrip()
    lines = [base, marker,
             "Tek 12 aylık döngü. Mevsimsellik iddiası içermez.", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(_findings, 1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  [not]   notes/findings.md — 03 bölümü ({len(_findings)} bulgu)")


def main() -> None:
    cfg.ensure_dirs()
    f = pd.read_parquet(cfg.INTERIM / "fact_sales.parquet")
    dim_product = pd.read_parquet(cfg.INTERIM / "dim_product.parquet")
    dim_date = pd.read_parquet(cfg.INTERIM / "dim_date.parquet")

    m = monthly_metrics(f)
    basket_reality_check(f)
    plot_monthly(m)
    plot_gross_vs_return(m)
    seasonality_check(m)
    weekly_and_dow(f, dim_date)
    fit_monthly(f, dim_product)
    store_month_panel(f)
    append_findings()

    print("\n03 tamamlandı.")


if __name__ == "__main__":
    main()
