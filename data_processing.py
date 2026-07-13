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
import re
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
# PART 1: Month-to-Date Loan Interest Insights
# ---------------------------------------------------------------------------

def map_responses(val):
    """Bucket raw survey responses into simplified interest categories."""
    if val in ['Yes']:
        return 'Interested Customer'
    if val in ['Yes, not valid permit', 'Yes, but not valid permit']:
        return 'Interested, no permit'
    if val in ['Yes, valid permit, but no proof of maturity',
               'Yes valid permit, but no proof of business maturity']:
        return 'Interested, no maturity'
    if val in ['No']:
        return 'Not Interested'
    return 'Other'


def filter_mtd_data(data: pd.DataFrame, monthago_date, report_date, active_cities):
    """Filter the raw survey data to the MTD window and active cities.

    Raises ReportDataError if required columns are missing or the resulting
    filtered frame is empty.
    """
    _require_columns(data, ['Completion time', 'Assigned City'], "Part 1 (MTD data)")

    data = data.copy()
    try:
        data['Completion time'] = pd.to_datetime(data['Completion time'])
    except Exception as e:
        raise ReportDataError(f"Part 1: could not parse 'Completion time' column as dates ({e}).")

    filtered_data = data[
        (data['Completion time'] >= monthago_date.normalize()) &
        (data['Completion time'] <= pd.Timestamp(report_date).normalize())
    ].copy()

    filtered_data = filtered_data[filtered_data['Assigned City'].isin(active_cities)]

    if filtered_data.empty:
        raise ReportDataError(
            "Part 1: no survey records found for the selected date range and active cities. "
            "Double-check the report date and your City/DSS mapping list."
        )

    return filtered_data


def compute_interest_summary(filtered_data: pd.DataFrame):
    """Compute the MTD interest crosstab (raw, for plotting) and the
    formatted summary table (for the HTML report).

    Returns (interest_summary_raw, interest_summary_formatted)
    """
    _require_columns(filtered_data, ['Interesado sa pautang?'], "Part 1 (interest column)")

    replace_vals_col1 = {
        'Yes, not valid permit': 'Yes, but not valid permit',
        'Yes, valid permit, but no proof of maturity': 'Yes valid permit, but no proof of business maturity'
    }
    for old_val, new_val in replace_vals_col1.items():
        filtered_data.loc[filtered_data['Interesado sa pautang?'] == old_val, 'Interesado sa pautang?'] = new_val

    interest_summary_raw = pd.crosstab(filtered_data['Assigned City'], filtered_data['Interesado sa pautang?'])

    if interest_summary_raw.empty:
        raise ReportDataError("Part 1: interest summary crosstab came back empty. No data to visualize.")

    interest_summary = interest_summary_raw.copy()
    interest_summary['Total Surveyed'] = interest_summary.sum(axis=1).apply(int)

    sa_cols = [col for col in filtered_data.columns if 'Assigned Sales Agent' in col]
    if not sa_cols:
        raise ReportDataError("Part 1: no 'Assigned Sales Agent' columns found to compute Survey Rate per SA.")

    tallied_SAs = filtered_data[['Assigned City'] + sa_cols].groupby('Assigned City').nunique().sum(axis=1)
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
    if 'Interesado sa pautang?' in cols:
        interest_summary = interest_summary.drop(columns=['Interesado sa pautang?'])
        cols = list(interest_summary.columns)

    cols_to_prioritize = ['Total Surveyed', 'Survey Rate per SA']
    cols = cols_to_prioritize + [c for c in cols if c not in cols_to_prioritize]
    interest_summary = interest_summary[cols]

    return interest_summary_raw, interest_summary


def extract_disinterest_responses(filtered_data: pd.DataFrame):
    """Pull cleaned free-text responses to the 'Bakit hindi interesado?' question."""
    target_col = 'Bakit hindi interesado?\n'
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

    Returns (report_df_dict, totals_df, cities_lst)
    """
    _require_columns(data, ['Completion time', 'Interesado sa pautang?'], "Part 2 (SA pivot data)")

    data = data.copy()
    try:
        data['Completion time'] = pd.to_datetime(data['Completion time'])
    except Exception as e:
        raise ReportDataError(f"Part 2: could not parse 'Completion time' column as dates ({e}).")

    asa_lst = [col for col in data.columns if 'Assigned Sales Agent' in col]
    if not asa_lst:
        raise ReportDataError("Part 2: no 'Assigned Sales Agent' columns found in the survey data.")

    cities_lst = []
    for loc_col in asa_lst:
        match = re.findall(r'\((.*?)\)', loc_col)
        if match:
            cities_lst.append(match[0])
    cities_lst = [c for c in cities_lst if c in active_cities]

    if not cities_lst:
        raise ReportDataError(
            "Part 2: none of the 'Assigned Sales Agent' city columns match your active City/DSS mapping list."
        )

    pivot_cols = ['Name of SA', 'Interested Customer', 'Interested, no permit',
                  'Interested, no maturity', 'Not Interested', 'Total Leads EOD']
    response_categories = ['Interested Customer', 'Interested, no permit',
                            'Interested, no maturity', 'Not Interested']

    report_df_dict = {}
    for loc_col in asa_lst:
        city_match = re.findall(r'\((.*?)\)', loc_col)
        if not city_match or city_match[0] not in active_cities:
            continue
        assigned_city = city_match[0]

        filtered_bydate = data[data['Completion time'].dt.date == report_date]
        filtered_bydate_byloc = filtered_bydate[~filtered_bydate[loc_col].isna()][[loc_col, 'Interesado sa pautang?']]

        if filtered_bydate_byloc.empty:
            report_df_dict[assigned_city] = pd.DataFrame(columns=pivot_cols)
            continue

        df_temp = filtered_bydate_byloc.copy()
        df_temp['Response_Group'] = df_temp['Interesado sa pautang?'].apply(map_responses)
        grouped = df_temp.groupby([loc_col, 'Response_Group']).size().unstack(fill_value=0).reindex(
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

    return report_df_dict, totals_df, cities_lst


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