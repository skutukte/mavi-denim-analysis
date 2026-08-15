"""04 — Fit × mağaza potansiyel alan analizi.

===========================================================================
POTANSİYEL TANIMI (açık ve tek cümlede)
===========================================================================
"Potansiyel alan" = anlamlı bir satış tabanı olan, TALEBİ BÜYÜYEN, büyümesini
İSKONTOYLA SATIN ALMAYAN ve sattığını İADE OLARAK GERİ VERMEYEN fit × mağaza
hücresidir.

Bu tanım dört bileşene ayrılır ve her biri ayrı ayrı ölçülür:

  1. BÜYÜME HIZI      (ağırlık %40)  — ilk 6 ay vs son 6 ay brüt satış
  2. İADE ORANI       (ağırlık %25)  — ters yönlü: düşük olan iyi
  3. İSKONTO YOĞUNLUĞU(ağırlık %20)  — ters yönlü: düşük olan iyi
  4. NET CİRO PAYI    (ağırlık %15)  — kanıt ağırlığı: hacim tabanı

---------------------------------------------------------------------------
SKORLAMA MANTIĞI — neden böyle
---------------------------------------------------------------------------
* Neden ham değer değil YÜZDELİK SIRA (percentile rank)?
  Dört metrik farklı birimlerde (oran, TL, endeks) ve dağılımları ağır çarpık
  (02'de görüldü: ciro Pareto, iade oranı 0-1 arası, iskonto sıfıra yığılmış).
  Ham değerleri toplamak en büyük ölçekli metriğin skoru ele geçirmesi demekti.
  Her bileşen kendi popülasyonu içinde 0-100 yüzdelik sıraya çevrilir, sonra
  ağırlıklı toplanır. Böylece tüm bileşenler aynı ölçekte yarışır.

* Neden büyüme en ağır bileşen (%40)?
  "Potansiyel" ileriye dönük bir iddiadır. Mevcut ciro geçmişi anlatır, büyüme
  yönü anlatır. Ancak tek başına yeterli değil — bu yüzden diğer üç bileşen
  büyümenin KALİTESİNİ sınar.

* Neden iade oranı bu kadar ağır (%25)?
  İade edilen satış ciro değildir; üstelik denim fit analizinde iade, kalıp-beden
  uyumsuzluğunun en doğrudan sinyalidir. İade oranı yüksek bir fitin büyümesi
  gerçek talep değil, deneme-iade döngüsü olabilir.

* Neden iskonto yoğunluğu cezalandırılıyor (%20)?
  İskontoyla satın alınan büyüme kalıcı değildir ve marjı yer. Aynı büyümeyi
  iskontosuz üreten hücre daha değerlidir.

* Neden ciro payının ağırlığı düşük (%15)?
  Hacim burada bir AMAÇ değil, KANIT AĞIRLIĞIDIR. Sıfır ağırlık verilseydi liste
  gürültülü küçük hücrelerle dolardı; yüksek ağırlık verilseydi skor sadece
  "zaten büyük olan" hücreleri tekrar sıralar, yani hiçbir şey keşfetmezdi.

* Neden büyüme oranı yerine SINIRLI BÜYÜME ENDEKSİ?
  Klasik (H2/H1 - 1) oranı H1=0 olduğunda sonsuza gider ve seyrek hücrelerde
  sıralamayı ele geçirir. Bunun yerine (H2-H1)/(H1+H2) kullanıldı: [-1, +1]
  aralığında sınırlı, simetrik ve H1=0 durumunu +1 olarak düzgün karşılıyor.

* Neden büyüme NET değil BRÜT satış üzerinden?
  Net ciro iade nedeniyle negatif olabiliyor; negatif değerlerde büyüme oranının
  işareti anlamını kaybediyor. Talep büyümesi brütten, iade kalitesi ayrı bir
  bileşenden ölçülüyor — iki sinyal birbirine karışmıyor.

---------------------------------------------------------------------------
HACİM EŞİĞİ — ve neden gizlenmiyor
---------------------------------------------------------------------------
12 ayda 10'dan az işlem satırı olan fit × mağaza hücreleri SKORLANMAZ; bu
hücrelerde büyüme ve iade oranı tek bir işlemle savrulur. Eşik altında kalan
hücreler silinmez: `04_fit_store_excluded.csv` dosyasına yazılır ve kapsam
raporunda kaç hücre / cironun yüzde kaçı dışarıda kaldığı açıkça belirtilir.

UYARI: İskonto yoğunluğu, 01'de kurulan DOĞRULANMAMIŞ varsayıma dayanır
(Amount net, brüt = Amount + DiscountAmount). Varsayım yanlışsa bu bileşen
yanlıştır; skor bu yüzden iskontosuz haliyle de ayrıca raporlanır.
===========================================================================

Input : data/interim/fact_sales.parquet, dim_product.parquet
Output: outputs/tables/04_*.csv, outputs/figures/04_*.png
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as cfg

C_SALES = "#2a78d6"
C_RETURN = "#e34948"
C_GRID = "#d8d8d4"
C_TEXT = "#52514e"
C_MUTED = "#b8b7b1"
C_HILITE = "#1baf7a"  # potansiyel çeyreği (kategorik slot 3)

# Skorlama ağırlıkları — toplamı 100. Gerekçeler modül docstring'inde.
WEIGHTS = {
    "growth_index": 40,          # yön: yüksek iyi
    "return_rate_amount": 25,    # yön: düşük iyi (ters çevrilir)
    "discount_intensity": 20,    # yön: düşük iyi (ters çevrilir)
    "net_share_pct": 15,         # yön: yüksek iyi (kanıt ağırlığı)
}
# True  = yüksek değer iyi
# False = düşük değer iyi (yüzdelik sıra ters çevrilir)
HIGHER_IS_BETTER = {
    "growth_index": True,
    "return_rate_amount": False,
    "discount_intensity": False,
    "net_share_pct": True,
}

MIN_ROWS = 10                    # hacim eşiği: 12 ayda en az 10 işlem satırı
H1_MONTHS = ["2024-02", "2024-03", "2024-04", "2024-05", "2024-06", "2024-07"]

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


# --------------------------------------------------------------------------
def compute_metrics(d: pd.DataFrame, keys: list[str], total_net: float) -> pd.DataFrame:
    """Verilen kırılımda dört bileşen metriğini hesaplar."""
    d = d.copy()
    d["in_h1"] = d.year_month.isin(H1_MONTHS)

    g = d.groupby(keys).agg(
        net_sales=("Amount", "sum"),
        gross_sales=("sales_amount", "sum"),
        return_amount=("return_amount", "sum"),
        discount_amount=("DiscountAmount", "sum"),
        net_qty=("Quantity", "sum"),
        n_rows=("DocID", "count"),
    )
    # Büyüme brüt satış üzerinden (net negatif olabiliyor, işaret anlamını kaybediyor)
    h = d.pivot_table(index=keys, columns="in_h1", values="sales_amount", aggfunc="sum", fill_value=0.0)
    g["gross_h1"] = h.get(True, pd.Series(0.0, index=g.index)).reindex(g.index).fillna(0.0)
    g["gross_h2"] = h.get(False, pd.Series(0.0, index=g.index)).reindex(g.index).fillna(0.0)

    # Sınırlı büyüme endeksi: (H2-H1)/(H1+H2) ∈ [-1, +1]; H1=0 → +1, H2=0 → -1
    denom = g.gross_h1 + g.gross_h2
    g["growth_index"] = np.where(denom > 0, (g.gross_h2 - g.gross_h1) / denom, np.nan)
    # Okunabilirlik için klasik oran da saklanır (skorda KULLANILMAZ, sonsuza gidebilir)
    g["growth_ratio_h2_h1"] = np.where(g.gross_h1 > 0, g.gross_h2 / g.gross_h1, np.nan)

    g["return_rate_amount"] = np.where(g.gross_sales > 0, g.return_amount.abs() / g.gross_sales, np.nan)

    # İskonto yoğunluğu — yalnızca satış satırları, varsayımsal brüt üzerinden
    s = d[~d.is_return].groupby(keys).agg(
        sale_amount=("Amount", "sum"), sale_discount=("DiscountAmount", "sum"))
    assumed_gross = s.sale_amount + s.sale_discount
    g["discount_intensity"] = (s.sale_discount / assumed_gross).where(assumed_gross > 0).reindex(g.index)

    g["net_share_pct"] = g.net_sales / total_net * 100
    return g.reset_index()


def score(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Dört bileşeni yüzdelik sıraya çevirip ağırlıklı toplar.

    Yüzdelik sıra HER POPÜLASYON İÇİNDE ayrı hesaplanır: fit seviyesi 10 fit
    arasında, fit × mağaza seviyesi skorlanan hücreler arasında. Yani iki
    tablodaki skorlar birbiriyle DOĞRUDAN KIYASLANAMAZ; her biri kendi
    listesinin iç sıralamasıdır.
    """
    out = df.copy()
    total_w = sum(WEIGHTS.values())
    out["potential_score"] = 0.0

    for col, w in WEIGHTS.items():
        pct = out[col].rank(pct=True, na_option="keep") * 100
        if not HIGHER_IS_BETTER[col]:
            pct = 100 - pct
        out[f"pctile_{col}"] = pct.round(1)
        # Bileşeni olmayan hücre o bileşenden nötr (50) puan alır; hücre elenmez.
        out["potential_score"] += pct.fillna(50) * w / total_w

    out["potential_score"] = out.potential_score.round(1)

    # İskontosuz duyarlılık skoru: iskonto varsayımı yanlışsa sıralama ne olurdu?
    w_no_disc = {k: v for k, v in WEIGHTS.items() if k != "discount_intensity"}
    tw = sum(w_no_disc.values())
    out["score_excl_discount"] = sum(
        out[f"pctile_{c}"].fillna(50) * w / tw for c, w in w_no_disc.items()
    ).round(1)

    out = out.sort_values("potential_score", ascending=False).reset_index(drop=True)
    out.insert(0, "rank", np.arange(1, len(out) + 1))
    print(f"  {label}: {len(out)} satır skorlandı")
    return out


# --------------------------------------------------------------------------
def scoring_definition_table() -> None:
    """Skorlama kurallarını veri olarak yazar — sunumda denetlenebilir olsun."""
    rows = [
        ("growth_index", WEIGHTS["growth_index"], "yüksek iyi",
         "(brüt_H2 - brüt_H1) / (brüt_H1 + brüt_H2), [-1,+1] aralığında sınırlı",
         "Potansiyel ileriye dönük bir iddiadır; yön en ağır sinyal."),
        ("return_rate_amount", WEIGHTS["return_rate_amount"], "düşük iyi",
         "|iade tutarı| / brüt satış",
         "İade edilen satış ciro değildir; denim fitte kalıp-beden uyumsuzluğunun doğrudan sinyali."),
        ("discount_intensity", WEIGHTS["discount_intensity"], "düşük iyi",
         "iskonto / varsayımsal brüt (yalnızca satış satırları)",
         "İskontoyla alınan büyüme kalıcı değildir ve marjı yer. VARSAYIMA DAYANIR."),
        ("net_share_pct", WEIGHTS["net_share_pct"], "yüksek iyi",
         "hücre net cirosu / toplam net ciro × 100",
         "Hacim amaç değil kanıt ağırlığı: küçük hücre gürültüsünü bastırır, listeyi ele geçirmez."),
    ]
    t = pd.DataFrame(rows, columns=["component", "weight_pct", "direction", "formula", "rationale"])
    cfg.save_table(t, "04_scoring_definition")

    cfg.log_assumption(
        "04'te 'potansiyel' şöyle tanımlandı: anlamlı satış tabanı olan, talebi büyüyen, büyümesini "
        f"iskontoyla satın almayan ve iade oranı düşük fit × mağaza hücresi. Skor = ağırlıklı yüzdelik "
        f"sıra (büyüme %{WEIGHTS['growth_index']}, iade %{WEIGHTS['return_rate_amount']}, "
        f"iskonto %{WEIGHTS['discount_intensity']}, ciro payı %{WEIGHTS['net_share_pct']}). "
        "Ağırlıklar analistin kararıdır, veriden türetilmemiştir; tanım ve gerekçe "
        "outputs/tables/04_scoring_definition.csv dosyasında."
    )


# --------------------------------------------------------------------------
def fit_level(d: pd.DataFrame, total_net: float) -> pd.DataFrame:
    cfg.header("04 — FİT × MAĞAZA POTANSİYEL ANALİZİ")
    print("\n-- Fit seviyesi --")

    fit = score(compute_metrics(d, ["fit"], total_net), "Fit seviyesi")
    cfg.save_table(fit.round(4), "04_fit_summary")
    cols = ["rank", "fit", "potential_score", "growth_index", "return_rate_amount",
            "discount_intensity", "net_share_pct"]
    print(fit[cols].round(3).to_string(index=False))
    return fit


def plot_fit_scorecard(fit: pd.DataFrame) -> None:
    """Bileşik skor + dört bileşen, aynı fit sırasıyla."""
    d = fit.sort_values("potential_score")

    fig = plt.figure(figsize=(15, 7.5))
    gs = fig.add_gridspec(2, 4, width_ratios=[1.45, 1, 1, 1], hspace=0.55, wspace=0.32)

    ax0 = fig.add_subplot(gs[:, 0])
    ax0.barh(d.fit, d.potential_score, color=C_SALES, height=0.66)
    for y, v in enumerate(d.potential_score):
        ax0.text(v + 1.5, y, f"{v:.0f}", va="center", fontsize=9, color=C_TEXT)
    style_axes(ax0, "Potansiyel skoru (0-100)", "", grid_axis="x")
    ax0.grid(axis="y", visible=False)
    ax0.set_xlim(0, 100)
    ax0.set_title("Bileşik potansiyel skoru", fontsize=11, color="#0b0b0b")

    panels = [
        ("growth_index", "Büyüme endeksi\n(H2 vs H1, [-1,+1])", lambda v: f"{v:.2f}", C_SALES, True),
        ("return_rate_amount", "İade oranı\n(düşük iyi)", lambda v: f"%{v * 100:.0f}", C_RETURN, False),
        ("discount_intensity", "İskonto yoğunluğu\n(düşük iyi, varsayımsal)", lambda v: f"%{v * 100:.0f}", C_RETURN, False),
        ("net_share_pct", "Net ciro payı\n(kanıt ağırlığı)", lambda v: f"%{v:.0f}", C_SALES, True),
    ]
    positions = [gs[0, 1], gs[0, 2], gs[0, 3], gs[1, 1]]
    for pos, (col, title, fmt, color, hib) in zip(positions, panels):
        ax = fig.add_subplot(pos)
        vals = d[col].fillna(0)
        ax.barh(d.fit, vals, color=color, height=0.62)
        style_axes(ax, "", "", grid_axis="x")
        ax.grid(axis="y", visible=False)
        ax.tick_params(labelsize=8)
        ax.xaxis.set_major_formatter(lambda v, _, fmt=fmt: fmt(v))
        if col == "growth_index":
            ax.axvline(0, color=C_TEXT, linewidth=1)
        ax.set_title(title, fontsize=9, color="#0b0b0b")

    ax_note = fig.add_subplot(gs[1, 2:])
    ax_note.axis("off")
    ax_note.text(
        0, 1,
        "POTANSİYEL TANIMI\n"
        "Anlamlı satış tabanı olan, talebi büyüyen,\n"
        "büyümesini iskontoyla satın almayan ve\n"
        "iade oranı düşük fit.\n\n"
        f"Skor = ağırlıklı yüzdelik sıra\n"
        f"  büyüme %{WEIGHTS['growth_index']}  ·  iade %{WEIGHTS['return_rate_amount']}  ·  "
        f"iskonto %{WEIGHTS['discount_intensity']}  ·  ciro payı %{WEIGHTS['net_share_pct']}\n\n"
        "Skorlar 10 fit ARASINDAKİ sıralamadır,\n"
        "mutlak bir başarı ölçüsü değildir.",
        fontsize=8.5, color=C_TEXT, va="top", family="monospace")

    fig.suptitle("Fit bazlı potansiyel skor kartı", fontsize=13, color="#0b0b0b", y=0.98)
    cfg.save_fig(fig, "04_fit_scorecard")

    top, bottom = fit.iloc[0], fit.iloc[-1]
    finding(
        f"Fit seviyesinde en yüksek potansiyel skoru {top.fit} ({top.potential_score:.0f}/100): büyüme endeksi "
        f"{top.growth_index:+.2f}, iade oranı %{top.return_rate_amount * 100:.0f}, iskonto yoğunluğu "
        f"%{top.discount_intensity * 100:.0f} ve net cironun %{top.net_share_pct:.0f}'i — yani büyümesini "
        f"iskontoya yaslamadan üretiyor; en düşük skor {bottom.fit} ({bottom.potential_score:.0f}/100)."
    )


def plot_potential_matrix(fit: pd.DataFrame) -> None:
    """Büyüme × iade matrisi; kabarcık = net ciro. Potansiyel çeyreği vurgulu."""
    x, y = fit.growth_index, fit.return_rate_amount
    xm, ym = x.median(), y.median()
    size = fit.net_sales.clip(lower=0) / fit.net_sales.max() * 1400 + 60
    # Potansiyel çeyreği: medyandan hızlı büyüyen VE medyandan az iade edilen
    is_potential = (x > xm) & (y < ym)

    fig, ax = plt.subplots(figsize=(11, 7))
    # Potansiyel çeyreği yalnızca "medyanın sağı VE medyanın altı" — tüm sütun değil.
    ax.add_patch(plt.Rectangle((xm, -0.02), x.max() + 0.22 - xm, ym + 0.02,
                               color=C_HILITE, alpha=0.06, zorder=0))
    ax.axvline(xm, color=C_MUTED, linestyle="--", linewidth=1.2)
    ax.axhline(ym, color=C_MUTED, linestyle="--", linewidth=1.2)

    ax.scatter(x[~is_potential], y[~is_potential], s=size[~is_potential], color=C_SALES,
               alpha=0.55, edgecolor="white", linewidth=2, zorder=3)
    ax.scatter(x[is_potential], y[is_potential], s=size[is_potential], color=C_HILITE,
               alpha=0.75, edgecolor="white", linewidth=2, zorder=4)

    for _, r in fit.iterrows():
        ax.annotate(f"{r.fit}\n{r.potential_score:.0f}", (r.growth_index, r.return_rate_amount),
                    textcoords="offset points", xytext=(0, 16), ha="center",
                    fontsize=8.5, color=C_TEXT, zorder=5)

    style_axes(ax, "Büyüme endeksi  (H2 vs H1, sağ = hızlanan talep)",
               "İade oranı  (aşağı = daha az iade)", grid_axis="both")
    ax.set_xlim(x.min() - 0.18, x.max() + 0.22)
    ax.set_ylim(-0.02, y.max() * 1.22)
    ax.yaxis.set_major_formatter(lambda v, _: f"%{v * 100:.0f}")
    # Etiket çeyreğin boş dip kısmına yerleşir, kabarcıklarla çakışmasın.
    ax.text((xm + x.max() + 0.22) / 2, 0.012, "POTANSİYEL ÇEYREĞİ\nhızlı büyüyen + az iade edilen",
            fontsize=9, color=C_HILITE, ha="center", va="bottom", weight="bold")
    ax.set_title("Potansiyel matrisi — büyüme × iade (kabarcık boyutu = net ciro)\n"
                 "Etiketlerdeki sayı bileşik potansiyel skorudur",
                 fontsize=11.5, color="#0b0b0b")
    cfg.save_fig(fig, "04_potential_matrix")

    names = fit[is_potential.values].fit.tolist()
    finding(
        f"Büyüme × iade matrisinde potansiyel çeyreğine (medyanın üstünde büyüme, altında iade) "
        f"{len(names)} fit düşüyor: {', '.join(names) if names else 'hiçbiri'} — "
        f"bu çeyrek net cironun %{fit[is_potential.values].net_share_pct.sum():.0f}'ini temsil ediyor, "
        f"yani büyüme ile iade kalitesini aynı anda tutturan alan cironun azınlığı."
    )


# --------------------------------------------------------------------------
def fit_store_level(d: pd.DataFrame, total_net: float) -> pd.DataFrame:
    """Fit × mağaza hücreleri — hacim eşiği ve kapsam raporuyla."""
    print("\n-- Fit × mağaza seviyesi --")

    cells = compute_metrics(d, ["fit", "StoreCode"], total_net)
    scored_mask = cells.n_rows >= MIN_ROWS
    scored, excluded = cells[scored_mask].copy(), cells[~scored_mask].copy()

    # Kapsam raporu — eşik altı hacim GİZLENMEZ
    cov = pd.DataFrame(
        [("min_rows_threshold", MIN_ROWS, "12 ayda hücre başına en az işlem satırı"),
         ("n_cells_total", len(cells), "dolu fit × mağaza hücresi"),
         ("n_cells_scored", len(scored), "eşiği geçen, skorlanan hücre"),
         ("n_cells_excluded", len(excluded), "eşik altı, skorlanmayan (silinmedi)"),
         ("net_share_scored_pct", round(scored.net_sales.sum() / cells.net_sales.sum() * 100, 1),
          "skorlanan hücrelerin net ciro payı (%)"),
         ("net_share_excluded_pct", round(excluded.net_sales.sum() / cells.net_sales.sum() * 100, 1),
          "eşik altı hücrelerin net ciro payı (%)"),
         ("n_stores_scored", scored.StoreCode.nunique(), "skorlamaya giren mağaza")],
        columns=["metric", "value", "description"])
    cfg.save_table(cov, "04_coverage_report")
    for _, r in cov.iterrows():
        print(f"  {r.metric:<24} {str(r.value):>8}   {r.description}")

    scored = score(scored, "Fit × mağaza")
    cfg.save_table(scored.round(4), "04_fit_store_potential")
    cfg.save_table(excluded.round(4), "04_fit_store_excluded")

    top = scored.head(25)[
        ["rank", "fit", "StoreCode", "potential_score", "score_excl_discount", "growth_index",
         "return_rate_amount", "discount_intensity", "net_sales", "n_rows"]]
    cfg.save_table(top.round(4), "04_top_opportunities")

    return scored


def plot_top_cells(scored: pd.DataFrame) -> None:
    """En yüksek skorlu 20 fit × mağaza hücresi."""
    top = scored.head(20).sort_values("potential_score")
    labels = [f"{r.fit} @ {int(r.StoreCode)}" for _, r in top.iterrows()]

    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(labels, top.potential_score, color=C_HILITE, height=0.66)
    for y, (_, r) in enumerate(top.iterrows()):
        ax.text(r.potential_score + 0.8, y,
                f"{r.potential_score:.0f}   büyüme {r.growth_index:+.2f} · iade %{r.return_rate_amount * 100:.0f} · "
                f"net {r.net_sales / 1e3:.0f}K",
                va="center", fontsize=8, color=C_TEXT)
    style_axes(ax, "Potansiyel skoru (0-100)", "", grid_axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 128)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_title(f"En yüksek potansiyelli 20 fit × mağaza hücresi\n"
                 f"(≥{MIN_ROWS} işlem satırı olan {len(scored):,} hücre arasından; "
                 f"tam liste 04_fit_store_potential.csv)",
                 fontsize=11, color="#0b0b0b")
    cfg.save_fig(fig, "04_top_opportunities")

    top1 = scored.iloc[0]
    n_top_fits = scored.head(50).fit.value_counts()
    finding(
        f"En yüksek potansiyelli hücre {top1.fit} @ mağaza {int(top1.StoreCode)} "
        f"(skor {top1.potential_score:.0f}, büyüme {top1.growth_index:+.2f}, iade "
        f"%{top1.return_rate_amount * 100:.0f}, net {top1.net_sales / 1e3:.0f}K TL); ilk 50 hücrenin "
        f"{n_top_fits.iloc[0]}'i {n_top_fits.index[0]} fitinden geliyor — potansiyel tek tek mağazalara değil "
        f"belirli fitlerin mağaza ağına yayılmasına bağlı."
    )


def plot_fit_store_heatmap(scored: pd.DataFrame) -> None:
    """Fit × mağaza skor matrisi — en çok hücresi olan mağazalar."""
    top_stores = (scored.groupby("StoreCode").net_sales.sum()
                  .sort_values(ascending=False).head(25).index.tolist())
    sub = scored[scored.StoreCode.isin(top_stores)]
    fit_order = (scored.groupby("fit").potential_score.mean()
                 .sort_values(ascending=False).index.tolist())
    mat = (sub.pivot_table(index="fit", columns="StoreCode", values="potential_score")
           .reindex(index=fit_order, columns=top_stores))
    cfg.save_table(mat.round(1).reset_index(), "04_fit_store_score_matrix")

    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list(
        "seq_blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
    fig, ax = plt.subplots(figsize=(13, 5))
    im = ax.imshow(mat.values, aspect="auto", cmap=cmap, vmin=0, vmax=100)
    ax.set_xticks(range(len(mat.columns)))
    ax.set_xticklabels([str(int(c)) for c in mat.columns], rotation=45, fontsize=8)
    ax.set_yticks(range(len(mat.index)))
    ax.set_yticklabels(mat.index, fontsize=9)
    ax.tick_params(colors=C_TEXT)
    ax.spines[:].set_visible(False)
    ax.set_xlabel("Mağaza kodu (en yüksek cirolu 25 mağaza)", fontsize=9, color=C_TEXT)
    # Boş hücre = eşiği geçemeyen kombinasyon; gri olarak okunur
    ax.set_facecolor("#f4f4f2")
    ax.set_title("Fit × mağaza potansiyel skoru (boş hücre = eşik altı, skorlanmadı)",
                 fontsize=11, color="#0b0b0b")
    cb = fig.colorbar(im, ax=ax, pad=0.012)
    cb.set_label("Potansiyel skoru", fontsize=8, color=C_TEXT)
    cb.ax.tick_params(labelsize=8, colors=C_TEXT)
    cb.outline.set_visible(False)
    cfg.save_fig(fig, "04_fit_store_heatmap")

    fill = mat.notna().sum().sum() / mat.size * 100
    finding(
        f"En yüksek cirolu 25 mağazada bile fit × mağaza matrisinin yalnızca %{fill:.0f}'i eşiği geçiyor; "
        f"mağaza ortalamasında en yüksek potansiyel {fit_order[0]}, en düşük {fit_order[-1]} — "
        f"aynı fitin skoru mağazadan mağazaya değiştiği için asortiman kararı fit bazında ülke geneli değil "
        f"mağaza kümesi bazında verilmeli."
    )


# --------------------------------------------------------------------------
def discount_sensitivity(scored: pd.DataFrame) -> None:
    """İskonto varsayımı yanlışsa sıralama ne kadar değişirdi?"""
    print("\n-- İskonto varsayımı duyarlılık kontrolü --")

    r1 = scored.potential_score.rank(ascending=False)
    r2 = scored.score_excl_discount.rank(ascending=False)
    corr = r1.corr(r2, method="spearman")
    top20_a = set(scored.nlargest(20, "potential_score").index)
    top20_b = set(scored.nlargest(20, "score_excl_discount").index)
    overlap = len(top20_a & top20_b)

    t = pd.DataFrame(
        [("spearman_rank_corr", round(corr, 4), "iskontolu vs iskontosuz skor sıra korelasyonu"),
         ("top20_overlap", overlap, "ilk 20'de ortak hücre sayısı"),
         ("top20_overlap_pct", overlap / 20 * 100, "ilk 20 örtüşme oranı (%)")],
        columns=["metric", "value", "description"])
    cfg.save_table(t, "04_discount_sensitivity")
    for _, r in t.iterrows():
        print(f"  {r.metric:<22} {str(r.value):>8}   {r.description}")

    finding(
        f"İskonto bileşeni doğrulanmamış bir varsayıma dayandığı için skor bu bileşen olmadan da "
        f"hesaplandı ve sonuç iki katmanlı: genel sıralama sağlam ({corr:.2f} Spearman korelasyonu), "
        f"AMA ilk 20 hücrenin yalnızca {overlap}'si ortak — yani hangi fitin genel olarak iyi olduğu "
        f"varsayımdan bağımsız, ancak 'en iyi 20 hücre' listesi doğrudan iskonto varsayımına bağlı ve "
        f"aksiyon alınmadan önce DiscountAmount'ın gerçek tanımı Mavi tarafına teyit ettirilmeli."
    )


def append_findings() -> None:
    path = cfg.NOTES / "findings.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "\n## 04 — Fit × mağaza potansiyel analizi\n"
    base = existing.split(marker)[0].rstrip()
    lines = [base, marker,
             "Potansiyel tanımı ve skor ağırlıkları: outputs/tables/04_scoring_definition.csv", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(_findings, 1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  [not]   notes/findings.md — 04 bölümü ({len(_findings)} bulgu)")


def main() -> None:
    cfg.ensure_dirs()
    f = pd.read_parquet(cfg.INTERIM / "fact_sales.parquet")
    dim_product = pd.read_parquet(cfg.INTERIM / "dim_product.parquet")
    d = f.merge(dim_product[["ProductCode", "fit"]], on="ProductCode",
                how="left", validate="many_to_one")
    total_net = d.Amount.sum()

    scoring_definition_table()
    fit = fit_level(d, total_net)
    plot_fit_scorecard(fit)
    plot_potential_matrix(fit)
    scored = fit_store_level(d, total_net)
    plot_top_cells(scored)
    plot_fit_store_heatmap(scored)
    discount_sensitivity(scored)
    append_findings()

    print("\n04 tamamlandı.")


if __name__ == "__main__":
    main()
