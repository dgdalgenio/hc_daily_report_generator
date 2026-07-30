"""
data_processing.py
-------------------
All pandas-level calculations for the MSME Report Generator.
No Streamlit calls live here - functions either return results or raise
a `ReportDataError` with a human-readable message that the wrapper (app.py)
can surface to the user.

Sections:
    - Part 1: Month-to-Date (MTD) loan interest insights
    - Part 2: SA Daily performance pivot tables per city
    - Part 3: Year-to-Date (YTD) signed contracts / financials / risk insights
"""

import calendar
import collections
from datetime import datetime

import pandas as pd


class ReportDataError(Exception):
    """Raised when uploaded data is missing required columns or is unusable."""
    pass


def _require_columns(df: pd.DataFrame, required_cols, context: str):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ReportDataError(
            f"{context}: missing required column(s) {missing}. "
            f"Please check the uploaded file's headers."
        )


# ---------------------------------------------------------------------------
# Shared helpers: city / agent parsing from the "Assigned Sales Agent" field
# ---------------------------------------------------------------------------
# The survey form now stores the assigned agent as a single free-text field
# formatted like "Taguig City - Jhon Michael Parco", while the city itself
# lives separately in the "Area" column. We treat "Area" as the source of
# truth for filtering/grouping, but cross-check it against the city prefix
# parsed out of "Assigned Sales Agent" and surface any mismatches as
# non-fatal warnings so bad form entries can be caught.

def _parse_city_from_agent(agent_str):
    if agent_str is None or (isinstance(agent_str, float) and pd.isna(agent_str)):
        return None
    parts = str(agent_str).split(' - ', 1)
    return parts[0].strip() if parts[0].strip() else None


def _parse_agent_name(agent_str):
    if agent_str is None or (isinstance(agent_str, float) and pd.isna(agent_str)):
        return 'Unassigned'
    parts = str(agent_str).split(' - ', 1)
    return parts[1].strip() if len(parts) > 1 and parts[1].strip() else str(agent_str).strip()


def _normalize_city(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ''
    s = str(s).lower().strip()
    s = s.split(',')[0].strip()      # drop province suffix, e.g. ", Nueva Ecija"
    s = s.replace(' city', '').strip()  # drop trailing/leading "City" word
    return s


def _find_city_mismatches(df: pd.DataFrame, area_col='Area', agent_col='Assigned Sales Agent'):
    """Cross-check Area vs the city prefix in Assigned Sales Agent.

    Returns a list of human-readable warning strings (empty if all match).
    """
    if area_col not in df.columns or agent_col not in df.columns:
        return []

    warnings = []
    for idx, row in df.iterrows():
        area = row.get(area_col)
        agent_city = _parse_city_from_agent(row.get(agent_col))
        if agent_city and _normalize_city(area) != _normalize_city(agent_city):
            warnings.append(
                f"Row {idx}: Area='{area}' does not match the city prefix in "
                f"Assigned Sales Agent ('{agent_city}')."
            )
    return warnings


# ---------------------------------------------------------------------------
# Result-of-Visit bucketing (visualization / Part 2 pivot only — the
# detailed Part 1 table keeps the raw dropdown values as-is, per business
# decision: granular "Result of Visit" categories are no longer collapsed
# in the detail views).
# ---------------------------------------------------------------------------

def bucket_result_of_visit(val):
    """Simple bucket classification used ONLY for chart visualization and
    the Part 2 SA pivot tables. Anything containing 'Not Interested' is
    Not Interested; anything containing 'Interested' or 'Eligible' is
    Interested/Eligible; everything else (Undecided, Store Closed, Refused
    Visit, etc.) falls into Other.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 'Other'
    s = str(val).strip().lower()
    if 'not interested' in s:
        return 'Not Interested'
    if 'interested' in s or 'eligible' in s:
        return 'Interested/Eligible'
    return 'Other'


# Kept as an alias so any other module importing the old name still works.
map_responses = bucket_result_of_visit


# ---------------------------------------------------------------------------
# PART 1: Month-to-Date Loan Interest Insights
# ---------------------------------------------------------------------------

def filter_mtd_data(data: pd.DataFrame, monthago_date, report_date, active_cities):
    """Filter the raw survey data to the MTD window and active cities.

    Raises ReportDataError if required columns are missing or the resulting
    filtered frame is empty.

    Returns (filtered_data, city_mismatch_warnings)
    """
    _require_columns(data, ['Completion time', 'Area', 'Assigned Sales Agent'], "Part 1 (MTD data)")

    data = data.copy()
    try:
        data['Completion time'] = pd.to_datetime(data['Completion time'])
    except Exception as e:
        raise ReportDataError(f"Part 1: could not parse 'Completion time' column as dates ({e}).")

    filtered_data = data[
        (data['Completion time'] >= monthago_date.normalize()) &
        (data['Completion time'] <= pd.Timestamp(report_date).normalize())
    ].copy()

    filtered_data = filtered_data[filtered_data['Area'].isin(active_cities)]

    if filtered_data.empty:
        raise ReportDataError(
            "Part 1: no survey records found for the selected date range and active cities. "
            "Double-check the report date and your City/DSS mapping list."
        )

    city_warnings = _find_city_mismatches(filtered_data)

    return filtered_data, city_warnings


def compute_interest_summary(filtered_data: pd.DataFrame):
    """Compute the MTD 'LatestResult' crosstab, kept UN-bucketed (raw
    dropdown values) as the detailed table for the HTML report, plus a
    simplified bucket crosstab (Interested/Eligible vs Not Interested vs
    Other) used only for the chart visualization.

    Returns (interest_summary_raw, interest_summary_formatted, bucket_summary_raw)
    """
    _require_columns(filtered_data, ['LatestResult'], "Part 1 (interest column)")

    interest_summary_raw = pd.crosstab(filtered_data['Area'], filtered_data['LatestResult'])

    if interest_summary_raw.empty:
        raise ReportDataError("Part 1: interest summary crosstab came back empty. No data to visualize.")

    filtered_data = filtered_data.copy()
    filtered_data['Interest Bucket'] = filtered_data['LatestResult'].apply(bucket_result_of_visit)
    bucket_summary_raw = pd.crosstab(filtered_data['Area'], filtered_data['Interest Bucket'])

    interest_summary = interest_summary_raw.copy()
    interest_summary['Total Surveyed'] = interest_summary.sum(axis=1).apply(int)

    sa_cols = [col for col in filtered_data.columns if 'Assigned Sales Agent' in col]
    if not sa_cols:
        raise ReportDataError("Part 1: no 'Assigned Sales Agent' column found to compute Survey Rate per SA.")

    tallied_SAs = filtered_data[['Area'] + sa_cols].groupby('Area').nunique().sum(axis=1)
    interest_summary['Survey Rate per SA'] = (interest_summary['Total Surveyed'] / tallied_SAs).round(2)

    for col in interest_summary.columns[:-2]:
        interest_summary[col] = interest_summary.apply(
            lambda row: f"{int(row[col])} ({(row[col] / row['Total Surveyed'] * 100):.2f}%)"
            if row['Total Surveyed'] else f"{int(row[col])} (0.00%)",
            axis=1
        )

    total_sum = interest_summary['Total Surveyed'].sum()
    if total_sum == 0:
        raise ReportDataError("Part 1: total surveyed count is zero; cannot compute percentages.")

    percentages = interest_summary['Total Surveyed'] / total_sum
    interest_summary['Total Surveyed'] = (
        interest_summary['Total Surveyed'].astype(str) +
        " (" + (percentages * 100).round(2).astype(str) + "%)"
    )

    cols = list(interest_summary.columns)
    if 'LatestResult' in cols:
        interest_summary = interest_summary.drop(columns=['LatestResult'])
        cols = list(interest_summary.columns)

    cols_to_prioritize = ['Total Surveyed', 'Survey Rate per SA']
    cols = cols_to_prioritize + [c for c in cols if c not in cols_to_prioritize]
    interest_summary = interest_summary[cols]

    return interest_summary_raw, interest_summary, bucket_summary_raw


def extract_disinterest_responses(filtered_data: pd.DataFrame):
    """Pull cleaned free-text responses to the 'Bakit ayaw sa Home Credit?' question."""
    target_col = 'Bakit ayaw sa Home Credit?'
    responses = filtered_data[target_col].unique() if target_col in filtered_data.columns else []
    clean_responses = [
        str(x).strip() for x in responses
        if x == x and str(x).lower() != 'nan' and str(x).strip() != ''
    ]
    return clean_responses


# ---------------------------------------------------------------------------
# PART 2: SA Daily Performance Pivot Tables per City
# ---------------------------------------------------------------------------

def build_city_pivot_tables(data: pd.DataFrame, report_date, active_cities):
    """Build per-city SA performance pivot dataframes for the given report_date.

    City is taken from the 'Area' column (cross-checked against the city
    prefix in 'Assigned Sales Agent'), and the SA name is parsed out of the
    'Assigned Sales Agent' field (format: "<City> - <Agent Name>"). Response
    grouping uses the simplified Interested/Eligible vs Not Interested vs
    Other bucket derived from 'LatestResult'.

    Returns (report_df_dict, totals_df, cities_lst, city_mismatch_warnings)
    """
    _require_columns(data, ['Completion time', 'Area', 'Assigned Sales Agent', 'LatestResult'],
                      "Part 2 (SA pivot data)")

    data = data.copy()
    try:
        data['Completion time'] = pd.to_datetime(data['Completion time'])
    except Exception as e:
        raise ReportDataError(f"Part 2: could not parse 'Completion time' column as dates ({e}).")

    cities_lst = [c for c in active_cities if c in set(data['Area'].dropna().unique())]

    if not cities_lst:
        raise ReportDataError(
            "Part 2: none of the survey data's 'Area' values match your active City/DSS mapping list."
        )

    filtered_bydate = data[data['Completion time'].dt.date == report_date]
    city_warnings = _find_city_mismatches(filtered_bydate)

    pivot_cols = ['Name of SA', 'Interested/Eligible', 'Not Interested', 'Other', 'Total Leads EOD']
    response_categories = ['Interested/Eligible', 'Not Interested', 'Other']

    report_df_dict = {}
    for assigned_city in cities_lst:
        filtered_bydate_byloc = filtered_bydate[
            filtered_bydate['Area'] == assigned_city
        ][['Assigned Sales Agent', 'LatestResult']].dropna(subset=['Assigned Sales Agent'])

        if filtered_bydate_byloc.empty:
            report_df_dict[assigned_city] = pd.DataFrame(columns=pivot_cols)
            continue

        df_temp = filtered_bydate_byloc.copy()
        df_temp['Name of SA'] = df_temp['Assigned Sales Agent'].apply(_parse_agent_name)
        df_temp['Response_Group'] = df_temp['LatestResult'].apply(bucket_result_of_visit)
        grouped = df_temp.groupby(['Name of SA', 'Response_Group']).size().unstack(fill_value=0).reindex(
            columns=response_categories, fill_value=0
        )
        grouped['Total Leads EOD'] = grouped.sum(axis=1)
        report_df = grouped.reset_index()
        report_df.columns = pivot_cols
        report_df_sorted = report_df.sort_values(by='Total Leads EOD', ascending=True)
        report_df_sorted.loc['Total'] = report_df.sum(axis=0)
        report_df_sorted.loc[report_df_sorted.index[-1], 'Name of SA'] = 'Total'
        report_df_dict[assigned_city] = report_df_sorted

    if not report_df_dict:
        raise ReportDataError("Part 2: no per-city pivot tables could be generated for the selected report date.")

    totals_df = pd.DataFrame()
    for city, city_df in report_df_dict.items():
        if not city_df.empty:
            totals_df[city] = city_df.loc['Total']

    if not totals_df.empty:
        totals_df = totals_df.transpose().drop(columns=['Name of SA'])
        totals_df.loc['Total'] = totals_df.sum(axis=0)

    return report_df_dict, totals_df, cities_lst, city_warnings


# ---------------------------------------------------------------------------
# PART 3: Year-to-Date Loans Insights (Contracts + Risk data)
# ---------------------------------------------------------------------------

def prepare_ytd_loans_data(contracts_data: pd.DataFrame, risk_data: pd.DataFrame):
    """Prepare and align contracts + risk data for the YTD visualization.

    Returns a dict of all series/frames needed by visuals.make_ytd_loans_chart.
    """
    month_map = {i: calendar.month_name[i] for i in range(1, 13)}
    contracts_data["Month"] = contracts_data["DATE_APPLICATION"].dt.month.map(month_map)
    
    _require_columns(contracts_data, ['Month', 'STATUS', 'IR', 'AMT ANNUITY', 'DISBURSED'],
                      "Part 3 (contracts data)")

    risk_month_col = "LocalDateTable_5a77bd3a-a070-4f8a-95cc-3ef5b6427ab8[Month]"
    if risk_month_col not in risk_data.columns:
        raise ReportDataError(
            f"Part 3 (risk data): expected PowerBI month column '{risk_month_col}' not found."
        )
    if "[FPD30__RISK]" not in risk_data.columns:
        raise ReportDataError("Part 3 (risk data): expected column '[FPD30__RISK]' not found.")

    contracts_data = contracts_data.copy()
    risk_data = risk_data.copy()

    current_month_num = datetime.now().month
    months = [calendar.month_name[i] for i in range(1, current_month_num + 1)]

    contracts_data["Month"] = pd.Categorical(contracts_data["Month"], categories=months, ordered=True)
    risk_data["Month"] = pd.Categorical(risk_data[risk_month_col], categories=months, ordered=True)

    signed_df = (
        contracts_data[contracts_data["STATUS"] == "Signed"]
        .groupby(["Month", "IR"], observed=False)
        .size()
        .unstack(fill_value=0)
    )

    if signed_df.empty:
        raise ReportDataError("Part 3: no 'Signed' contracts found in the contracts data.")

    target_irs = [0.0399, 0.0499]
    for ir in target_irs:
        if ir not in signed_df.columns:
            signed_df[ir] = 0

    annuity_sums = contracts_data.groupby("Month", observed=False)["AMT ANNUITY"].sum() / 1000
    disbursed_sums = contracts_data.groupby("Month", observed=False)["DISBURSED"].sum() / 1000
    risk_series = risk_data.groupby("Month", observed=False)["[FPD30__RISK]"].first()

    return {
        "months": months,
        "signed_df": signed_df,
        "target_irs": target_irs,
        "annuity_sums": annuity_sums,
        "disbursed_sums": disbursed_sums,
        "risk_series": risk_series,
    }