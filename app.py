"""
app.py
------
MSME Client Survey & SA Performance Report Generator - Streamlit wrapper.

The following are supporting files for the app:
    data_processing.py   -> pandas calculations for Part 1 / 2 / 3
    visuals.py            -> matplotlib chart builders
    ai_narrative.py        -> AI-powered / fallback narrative text
    excel_report.py        -> styled Part 2 Excel workbook + HTML conversion
    email_template.py      -> dynamic/adaptive final email HTML assembly
"""

from datetime import datetime, timedelta

import pandas as pd
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

import streamlit as st

from data_processing import (
    ReportDataError,
    filter_mtd_data,
    compute_interest_summary,
    extract_disinterest_responses,
    build_city_pivot_tables,
    prepare_ytd_loans_data,
)
from visuals import make_mtd_loan_interest_chart, make_ytd_loans_chart
from ai_narrative import generate_narrative
from excel_report import build_city_pivot_workbook
from email_template import (
    save_interest_summary_as_html_string,
    build_email_report,
    _part1_section_html,
    _part2_section_html,
    _part3_section_html,
)

# --- STREAMLIT SERVER CONFIG ---
st.config.set_option("server.maxUploadSize", 500)
st.config.set_option("server.enableCORS", False)
st.config.set_option("server.enableXsrfProtection", False)

st.set_page_config(page_title="MSME Report Generator", page_icon="📊", layout="wide")

# --- UI HEADER ---
st.title("📊 MSME Client Survey & SA Performance Report Generator")
st.markdown("Convert raw survey data into clean email-ready HTML summaries instantly.")

st.sidebar.header("📋 Report Configurations")

# --- SECTION TOGGLES ---
st.sidebar.subheader("🧩 Report Sections")
include_part1 = st.sidebar.toggle("Part 1: Month-to-Date Insights", value=True)
include_part2 = st.sidebar.toggle("Part 2: SA Daily Reports per City", value=True)
include_part3 = st.sidebar.toggle("Part 3: Year-to-Date Loans Insights", value=False)
if include_part3:
    st.sidebar.caption(
        "Part 3 is turned on - the Contracts and Risk data files below are required."
    )

# --- FILE UPLOADS ---
st.sidebar.subheader("📁 Data Uploads")
needs_survey_file = include_part1 or include_part2
uploaded_file = st.sidebar.file_uploader(
    f"Upload MSME Client Survey Form (Excel){' *' if needs_survey_file else ''}",
    type=["xlsx"]
)
contracts_data_file = st.sidebar.file_uploader(
    f"Upload Downloaded Contracts Data from PowerBI (Excel){' *' if include_part3 else ''}",
    type=["xlsx"]
)
risk_data_file = st.sidebar.file_uploader(
    f"Upload Downloaded Risk Data from PowerBI (Excel){' *' if include_part3 else ''}",
    type=["xlsx"]
)

# --- DATE SELECTOR ---
yesterday = (datetime.today() - timedelta(days=1)).date()
report_date = st.sidebar.date_input("Select Report Date", value=yesterday)

# --- SIGNATURE ---
st.sidebar.subheader("✍️ Report Signature")
report_signature = st.sidebar.text_input(
    "Sign off name",
    placeholder="e.g., Red, Operations Team, Management",
    help="Changes the trailing sign-off name at the bottom of the generated email."
)

# --- AI ENGINE (only relevant to Part 1) ---
st.sidebar.subheader("🤖 Cloud AI Insights Engine")
ai_mode = st.sidebar.selectbox(
    "Select Model Engine",
    [
        "Groq Cloud API (Free / Llama-3.1)",
        "GitHub Models (Free via Microsoft/GitHub Account)",
        "Google Gemini API (Free Tier)",
        "OpenAI GPT-4o API",
        "Algorithmic Text Engine (Fallback / Free)"
    ],
    disabled=not include_part1,
    help=("Only used for Part 1's 'Common Reasons for Disinterest' narrative."
          if include_part1 else "Enable Part 1 to use this setting.")
)
api_key = st.sidebar.text_input(f"Enter {ai_mode.split(' ')[0]} API Key", type="password", disabled=not include_part1)

# --- LOCATION TO DSS MAPPING (only needed for Part 1 / Part 2) ---
st.sidebar.subheader("📍 Location to DSS Mapping")

if "cities_dict" not in st.session_state:
    st.session_state.cities_dict = {
        'QC': ('Fitzgerald De Leon', 'fitzgerald.deleon@homecredit.ph'),
        'Taguig': ('Edwin Jr Atendido', 'edwin.atendido@homecredit.ph'),
        'Mexico, Pampanga': ('Arjon Omega', 'arjon.omega@homecredit.ph'),
        'Lipa, Batangas': ('Nikko Seno', 'nikko.seno@homecredit.ph'),
        'Dasmarinas, Cavite': ('Danny Gasper', 'danny.gasper@homecredit.ph'),
        'Cabanatuan, Nueva Ecija': ('Joshua Benedicto', 'joshua.benedicto@homecredit.ph')
    }

with st.sidebar.expander("➕ Add a New City/Location"):
    new_city_name = st.text_input("Enter New City Name (Must match Excel column name exactly)")
    if st.button("Add City to List", use_container_width=True):
        if new_city_name and new_city_name not in st.session_state.cities_dict:
            st.session_state.cities_dict[new_city_name] = ("", "")
            st.success(f"Added '{new_city_name}' successfully!")
            st.rerun()

location_to_dss_dict = {}
with st.sidebar.expander("✏️ Edit DSS & Email Assignments", expanded=False):
    for city, (def_name, def_email) in list(st.session_state.cities_dict.items()):
        st.markdown(f"**{city}**")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", value=def_name, key=f"name_{city}")
        with col2:
            email = st.text_input("Email", value=def_email, key=f"email_{city}")
        st.session_state.cities_dict[city] = (name, email)
        location_to_dss_dict[city] = {'name': name, 'email': [email]}

# --- READINESS CHECK ---
survey_ready = (not needs_survey_file) or (uploaded_file is not None)
part3_ready = (not include_part3) or (contracts_data_file is not None and risk_data_file is not None)
can_process = survey_ready and part3_ready and (include_part1 or include_part2 or include_part3)

if not include_part1 and not include_part2 and not include_part3:
    st.info("Turn on at least one report section (Part 1, Part 2, or Part 3) to proceed.")
elif not can_process:
    missing_bits = []
    if needs_survey_file and uploaded_file is None:
        missing_bits.append("the MSME Client Survey Excel file")
    if include_part3 and contracts_data_file is None:
        missing_bits.append("the Contracts data Excel file")
    if include_part3 and risk_data_file is None:
        missing_bits.append("the Risk data Excel file")
    st.info(
        "Welcome! Please upload " + " and ".join(missing_bits or ["the required data file(s)"]) +
        " in the sidebar to begin."
    )

# --- PROCESSING PIPELINE ---
if can_process:
    if st.button("🚀 Process Data and Compile Report", type="primary"):
        with st.spinner("Processing calculations and compiling assets... Please wait."):

            sections = []          # ordered list of {"title","label","body_html"} for the email
            preview_assets = {}    # holds bytes/dataframes for the preview tabs
            section_errors = []    # collected non-fatal error messages

            active_cities = list(location_to_dss_dict.keys())

            # ============================ PART 1 ============================
            if include_part1:
                try:
                    data = pd.read_excel(uploaded_file)
                    monthago_date = pd.Timestamp(report_date - relativedelta(days=1, months=1))

                    filtered_data = filter_mtd_data(data, monthago_date, report_date, active_cities)
                    interest_summary_raw, interest_summary = compute_interest_summary(filtered_data)

                    raw_png_bytes, img_html = make_mtd_loan_interest_chart(
                        interest_summary_raw, monthago_date, report_date
                    )
                    mtd_table_html = save_interest_summary_as_html_string(interest_summary)

                    clean_responses = extract_disinterest_responses(filtered_data)
                    formatted_txt = generate_narrative(
                        clean_responses, ai_mode, api_key, warn_fn=st.warning
                    )

                    sections.append({
                        "title": "Quick Insights (Month-to-Date Data)",
                        "label": "our Month-to-Date (MTD) survey insights",
                        "body_html": _part1_section_html(img_html, mtd_table_html, formatted_txt),
                    })
                    preview_assets["part1"] = {
                        "raw_png_bytes": raw_png_bytes,
                        "formatted_txt": formatted_txt,
                    }
                except ReportDataError as e:
                    section_errors.append(f"Part 1 skipped: {e}")
                except Exception as e:
                    section_errors.append(f"Part 1 failed unexpectedly: {e}")

            # ============================ PART 2 ============================
            if include_part2:
                try:
                    # Re-read a fresh copy so Part 1's in-place edits don't leak in
                    data2 = pd.read_excel(uploaded_file)
                    report_df_dict, totals_df, cities_lst = build_city_pivot_tables(
                        data2, report_date, active_cities
                    )
                    wb, raw_xlsx_bytes, excel_html_content = build_city_pivot_workbook(
                        report_df_dict, totals_df, location_to_dss_dict, cities_lst, report_date
                    )

                    sections.append({
                        "title": "SA Reports per City",
                        "label": "operational SA performance metrics across all cities",
                        "body_html": _part2_section_html(excel_html_content),
                    })
                    preview_assets["part2"] = {
                        "raw_xlsx_bytes": raw_xlsx_bytes,
                        "totals_df": totals_df,
                    }
                except ReportDataError as e:
                    section_errors.append(f"Part 2 skipped: {e}")
                except Exception as e:
                    section_errors.append(f"Part 2 failed unexpectedly: {e}")

            # ============================ PART 3 ============================
            if include_part3:
                try:
                    contracts_data = pd.read_excel(contracts_data_file)
                    risk_data = pd.read_excel(risk_data_file)

                    ytd_data = prepare_ytd_loans_data(contracts_data, risk_data)
                    ytd_png_bytes, ytd_img_html = make_ytd_loans_chart(ytd_data)

                    sections.append({
                        "title": "Year-to-Date Loans Insights",
                        "label": "year-to-date signed contract, financial, and risk performance",
                        "body_html": _part3_section_html(ytd_img_html),
                    })
                    preview_assets["part3"] = {
                        "raw_png_bytes": ytd_png_bytes,
                    }
                except ReportDataError as e:
                    section_errors.append(f"Part 3 skipped: {e}")
                except Exception as e:
                    section_errors.append(f"Part 3 failed unexpectedly: {e}")

            # ============================ SURFACE ERRORS ============================
            for msg in section_errors:
                st.warning(f"⚠️ {msg}")

            if not sections:
                st.error("No report sections could be generated. Please review the warnings above.")
            else:
                final_signoff = report_signature.strip() if report_signature.strip() else "MSME System Administrator"
                email_template = build_email_report(report_date, final_signoff, sections)

                st.success(f"🎉 Report compiled with {len(sections)} section(s)!")

                # --- PREVIEW TABS (dynamic based on what actually ran) ---
                st.markdown("### 🔍 Internal File Output Pipelines")
                tab_labels = ["📬 email_ready.html (Preview)"]
                if "part1" in preview_assets:
                    tab_labels.append("📈 loan_interests.png")
                    tab_labels.append("📝 bakit_hindi.txt (AI Layout)")
                if "part2" in preview_assets:
                    tab_labels.append("🗃️ pivot_tables.xlsx")
                if "part3" in preview_assets:
                    tab_labels.append("📊 ytd_loans_insights.png")

                tabs = st.tabs(tab_labels)
                tab_iter = iter(tabs)

                with next(tab_iter):
                    st.components.v1.html(email_template, height=600, scrolling=True)
                    st.download_button(
                        label="📥 Download: email_ready.html",
                        data=email_template,
                        file_name=f"{report_date} email_ready.html",
                        mime="text/html",
                        use_container_width=True
                    )

                if "part1" in preview_assets:
                    with next(tab_iter):
                        st.image(preview_assets["part1"]["raw_png_bytes"], use_container_width=True)
                        st.download_button(
                            label="📥 Download: loan interests.png",
                            data=preview_assets["part1"]["raw_png_bytes"],
                            file_name=f"{report_date} loan interests.png",
                            mime="image/png",
                            use_container_width=True
                        )
                    with next(tab_iter):
                        clean_text_preview = BeautifulSoup(
                            preview_assets["part1"]["formatted_txt"], "html.parser"
                        ).get_text(separator="\n")
                        st.text_area("Generated Structural Narrative Layout:", value=clean_text_preview, height=300)
                        st.download_button(
                            label="📥 Download: bakit hindi.txt",
                            data=clean_text_preview,
                            file_name=f"{report_date} bakit hindi.txt",
                            mime="text/plain",
                            use_container_width=True
                        )

                if "part2" in preview_assets:
                    with next(tab_iter):
                        totals_df = preview_assets["part2"]["totals_df"]
                        st.dataframe(totals_df if not totals_df.empty else pd.DataFrame(), use_container_width=True)
                        st.download_button(
                            label="📥 Download: pivot tables.xlsx",
                            data=preview_assets["part2"]["raw_xlsx_bytes"],
                            file_name=f"{report_date} pivot tables.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )

                if "part3" in preview_assets:
                    with next(tab_iter):
                        st.image(preview_assets["part3"]["raw_png_bytes"], use_container_width=True)
                        st.download_button(
                            label="📥 Download: ytd loans insights.png",
                            data=preview_assets["part3"]["raw_png_bytes"],
                            file_name=f"{report_date} ytd loans insights.png",
                            mime="image/png",
                            use_container_width=True
                        )
                        
st.markdown(
    """
    <style>
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        text-align: center;
        padding: 10px;
        font-size: 14px;
    }
    </style>
    <div class="footer">
        © July 2026, by Deanne Algenio
    </div>
    """,
    unsafe_allow_html=True
)
