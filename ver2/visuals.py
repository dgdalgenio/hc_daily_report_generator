"""
visuals.py
----------
Matplotlib chart builders. Every function renders a chart to an in-memory
PNG buffer and returns both the raw PNG bytes and a ready-to-embed base64
<img> HTML snippet, so callers never have to touch matplotlib directly.
"""

import base64
import collections
import io

import matplotlib.pyplot as plt


def _fig_to_png_and_html(fig, alt_text):
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format='png', dpi=300, bbox_inches="tight")
    img_buffer.seek(0)
    raw_png_bytes = img_buffer.getvalue()
    b64_string = base64.b64encode(raw_png_bytes).decode('utf-8')
    img_html = (
        f'<img src="data:image/png;base64,{b64_string}" alt="{alt_text}" '
        f'style="max-width:100%; height:auto;"><br>'
    )
    plt.close(fig)
    return raw_png_bytes, img_html


def make_mtd_loan_interest_chart(interest_summary_raw, monthago_date, report_date):
    """Part 1 chart: stacked bar (volume) + line (rate) of loan interest by city."""
    df_viz = interest_summary_raw.copy()
    totals = df_viz.sum(axis=1)
    rates = df_viz.div(totals, axis=0)

    fig, ax1 = plt.subplots(figsize=(10, 6))
    line_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    bar_colors = ['#5A80A4', '#E08E69', '#7EA172', '#C97A7E', '#9381A4', '#D9B48F']

    df_viz.plot(kind='bar', stacked=True, ax=ax1, color=bar_colors[:len(df_viz.columns)], alpha=0.7, legend=False)
    ax1.set_ylabel('Total Volume', color='#4A4A4A')
    ax1.set_xlabel('Assigned City')
    ax1.set_xticklabels(df_viz.index, rotation=45, ha='right')

    ax2 = ax1.twinx()
    for i, col in enumerate(rates.columns):
        ax2.plot(rates.index, rates[col], marker='o', label=col,
                  color=line_colors[i % len(line_colors)], linewidth=2.5)

    x_groups = collections.defaultdict(list)
    for key in rates.keys():
        for i, val in enumerate(rates[key]):
            x_groups[i].append((val, key))

    for i, items in x_groups.items():
        items.sort(key=lambda x: x[0])
        num_points = len(items)
        for index, (val, key) in enumerate(items):
            offset = (0, -12) if index == 0 else (0, 10) if index == num_points - 1 else (10 if index % 2 == 0 else -10, 5)
            va = 'top' if index == 0 else 'bottom'
            ax2.annotate(f'{val:.0%}', (i, val), textcoords="offset points", xytext=offset,
                         ha='center', va=va, fontsize=9,
                         fontweight='bold' if key == 'No' else 'normal', color='#1D3557')

    ax2.set_ylabel('Rate (%)')
    ax2.set_ylim(0, 1)
    ax2.legend(title='Interesado sa pautang?', loc='lower center', bbox_to_anchor=(0.5, 0.92),
               bbox_transform=fig.transFigure, ncols=2)
    plt.grid(True, linestyle='--', linewidth=0.8, color='gray', alpha=0.4)
    plt.title(f'Loan Interest: Volume and Rate by City ({monthago_date.strftime("%B %d")} - {report_date.strftime("%B %d")})')
    plt.tight_layout()

    return _fig_to_png_and_html(fig, "MTD Loan Interests Chart")


def make_ytd_loans_chart(ytd_data: dict):
    """Part 3 chart: signed contract volume (stacked bar) vs annuity/disbursed
    (line) vs FPD30 risk (dashed line), by month, year-to-date."""
    signed_df = ytd_data["signed_df"]
    annuity_sums = ytd_data["annuity_sums"]
    disbursed_sums = ytd_data["disbursed_sums"]
    risk_series = ytd_data["risk_series"]

    fig, ax1 = plt.subplots(figsize=(14, 7))

    color_ir399 = "#EAEAEA"
    color_ir499 = "#CCCCCC"
    width = 0.4

    bar1 = ax1.bar(signed_df.index, signed_df[0.0399], color=color_ir399, width=width,
                    label="Signed (IR: 3.99%)")
    bar2 = ax1.bar(signed_df.index, signed_df[0.0499], bottom=signed_df[0.0399], color=color_ir499,
                    width=width, label="Signed (IR: 4.99%)")

    ax1.set_xlabel("Month", labelpad=12)
    ax1.set_ylabel("Signed Contract Vol. (Stacked)", color="gray")
    ax1.tick_params(axis="y", labelcolor="gray")
    ax1.grid(axis="y", linestyle=":", alpha=0.5)

    for index, row in signed_df.iterrows():
        total_val = row[0.0399] + row[0.0499]
        if total_val > 0:
            ax1.annotate(f"{int(total_val)}", xy=(index, total_val), xytext=(0, 4),
                         textcoords="offset points", ha="center", va="bottom",
                         color="dimgray", fontsize=9)

    ax2 = ax1.twinx()
    line1 = ax2.plot(annuity_sums.index, annuity_sums.values, color="#4A4A4A", marker="o",
                      linewidth=2.5, label="Annuity (Sum)")
    line2 = ax2.plot(disbursed_sums.index, disbursed_sums.values, color="#D9383A", marker="o",
                      linewidth=2.5, label="Disbursed (Sum)")

    ax2.set_ylabel("Financial Amount (in \u20b1K)", color="black")
    ax2.tick_params(axis="y", labelcolor="black")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: f"\u20b1{x:.1f}K"))

    for x, y in zip(annuity_sums.index, annuity_sums.values):
        ax2.annotate(f"\u20b1{y:.1f}K", xy=(x, y), xytext=(0, -16), textcoords="offset points",
                     ha="center", color="#4A4A4A", fontsize=9)
    for x, y in zip(disbursed_sums.index, disbursed_sums.values):
        ax2.annotate(f"\u20b1{y:.1f}K", xy=(x, y), xytext=(0, 10), textcoords="offset points",
                     ha="center", color="#D9383A", fontsize=9)

    ax3 = ax1.twinx()
    ax3.spines["right"].set_position(("axes", 1.11))

    line3 = ax3.plot(risk_series.index, risk_series.values, color="#1F77B4", marker="s",
                      linestyle="--", linewidth=2, label="FPD30 Risk")

    ax3.set_ylabel("FPD30 Risk (%)", color="#1F77B4")
    ax3.tick_params(axis="y", labelcolor="#1F77B4")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: f"{x*100:.1f}%"))

    import pandas as pd
    for x, y in zip(risk_series.index, risk_series.values):
        if pd.notna(y):
            ax3.annotate(f"{y*100:.1f}%", xy=(x, y), xytext=(0, 10), textcoords="offset points",
                         ha="center", color="#1F77B4", fontsize=9)

    plt.title("Signed Contracts Volume vs Financials & FPD30 Risk Performance", fontsize=14, pad=22)

    all_elements = [bar1, bar2] + line1 + line2 + line3
    all_labels = [element.get_label() for element in all_elements]
    ax1.legend(all_elements, all_labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=5)

    plt.tight_layout()

    return _fig_to_png_and_html(fig, "YTD Loans Insights Chart")