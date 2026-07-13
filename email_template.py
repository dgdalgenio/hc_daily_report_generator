"""
email_template.py
------------------
Builds the final email-ready HTML report. The template is dynamic/adaptive:
each of Part 1, Part 2, and Part 3 is only rendered if it was (a) toggled on
and (b) actually produced usable content. Section numbering ("Part 1",
"Part 2"...) is recalculated on the fly so there are never gaps like
"Part 1, Part 3" if Part 2 was skipped.
"""

from io import StringIO

import pandas as pd


BASE_STYLE = """
<style>
    body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #333333; line-height: 1.6; }
    h1 { color: #002060; border-bottom: 2px solid #002060; padding-bottom: 5px; font-size: 16pt; }
    h2 { color: #1F4E79; font-size: 13pt; margin-top: 20px; }
    h3 { color: #595959; font-size: 11pt; margin-bottom: 5px; }
    .section { margin-bottom: 35px; }
    .insight-box { background: #F2F4F7; border-left: 5px solid #002060; margin: 15px 0; padding: 15px; border-radius: 4px; }
</style>
"""


def save_interest_summary_as_html_string(interest_summary: pd.DataFrame):
    """Renders the MTD interest summary dataframe as a styled HTML table string."""
    html_table = interest_summary.reset_index().to_html(
        index=False,
        classes="table table-striped custom-loan-table"
    )

    df = pd.read_html(StringIO(html_table))[0]
    df = df.drop(columns=["Interesado sa pautang?"], errors="ignore")

    html_table = df.to_html(
        index=False,
        classes="table table-striped custom-loan-table"
    )

    custom_css = """
    <style>
        .custom-loan-table { width: 100%; table-layout: fixed; border-collapse: collapse; }
        .custom-loan-table th:nth-child(1), .custom-loan-table td:nth-child(1) { width: 16%; text-align: left; }
        .custom-loan-table th:not(:nth-child(1)), .custom-loan-table td:not(:nth-child(1)) { width: 14%; text-align: center; }
    </style>
    """
    return custom_css + html_table


def _part1_section_html(img_html, mtd_table_html, formatted_txt):
    return f"""
    <h2>1. Month-to-Date Interest and Requirement Rates</h2>
    <div style="margin-bottom: 20px; text-align: center;">
        <div style="display: inline-block; width: 80%;">
            {img_html}
        </div>
    </div>
    <div>{mtd_table_html}</div>
    <br>
    <h2>2. Common Reasons for Disinterest &amp; Other Insights</h2>
    <div class="insight-box">{formatted_txt}</div>
    """


def _part2_section_html(excel_html_content):
    return f"{excel_html_content}"


def _part3_section_html(img_html):
    return f"""
    <h2>1. Signed Contracts Volume vs Financials &amp; FPD30 Risk (Year-to-Date)</h2>
    <div style="margin-bottom: 20px; text-align: center;">
        <div style="display: inline-block; width: 100%;">
            {img_html}
        </div>
    </div>
    """


def build_email_report(report_date, final_signoff, sections: list):
    """Assembles the final email HTML.

    `sections` is an ordered list of dicts, each with:
        {"title": "Part n: <title>", "body_html": "<...>"}
    Only sections that were actually built (toggled on & successfully
    computed) should be passed in - numbering is derived from list order,
    so gaps never appear.
    """
    intro_bits = []
    for idx, sec in enumerate(sections, start=1):
        intro_bits.append(sec["label"])

    if intro_bits:
        combined_desc = ", ".join(intro_bits[:-1])
        if len(intro_bits) > 1:
            combined_desc += f", and {intro_bits[-1]}"
        else:
            combined_desc = intro_bits[0]
    else:
        combined_desc = "the requested report sections"

    body_sections_html = ""
    for idx, sec in enumerate(sections, start=1):
        body_sections_html += f"""
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
        <div class="section">
            <h1>Part {idx}: {sec['title']}</h1>
            {sec['body_html']}
        </div>
        """

    if not sections:
        body_sections_html = """
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
        <div class="section">
            <p><b>No report sections were available to include.</b> Please check your uploaded files,
            toggles, and report date, then try again.</p>
        </div>
        """

    email_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        {BASE_STYLE}
    </head>
    <body>
        <p>Dear Team,</p>
        <p>Please find below the consolidated <b>Daily MSME Client Survey and SA Performance Report</b> for
        <b>{report_date.strftime("%B %d, %Y")}</b>. This update combines {combined_desc}.</p>
        {body_sections_html}
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
        <p>Best regards,<br>-{final_signoff}</p>
    </body>
    </html>
    """
    return email_template