import streamlit as st
import pandas as pd
from pathlib import Path
import re
from functools import reduce
import io

st.set_page_config(page_title="IMPACT Progress Data Standardization", layout="wide")

st.markdown(
    """
    <style>
        h1 {
            border-bottom: 3px solid #007680;
            padding-bottom: 6px;
            color: #51534a;
            display:inline-block;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# st.set_page_config(page_title="IMPACT Progress Data Standardization", layout="wide")


# ---------------- STATE INIT ----------------
if "final" not in st.session_state:
    st.session_state.final = None

if "processed" not in st.session_state:
    st.session_state.processed = False

if "last_signature" not in st.session_state:
    st.session_state.last_signature = None


# ---------------- LOAD QUESTION BANK ----------------
@st.cache_data
def load_question_bank():
    try:
        # qn_path = Path.cwd().parent / "31032026_IMPACT_Progress_Survey_Bank.xlsx"
        return pd.read_excel("31032026_IMPACT_Progress_Survey_Bank.xlsx", sheet_name="stability", header=12)
    except Exception:
        return None


qn_bank = load_question_bank()

if qn_bank is None:
    st.error("System error: Unable to load required configuration file.")
    st.stop()


# ---------------- PROCESSING FUNCTION ----------------
def process_files(qn_bank, survey_files, manager_name):
    qn_bank = qn_bank.copy()
    qn_bank["qno_q_group"] = qn_bank["qno"].astype(str) + "_" + qn_bank["q_group"].astype(str)

    mapping = {
        "TRANSDATE": 1106,
        "FARMER_NAME": 1201,
        "FARMER_CODE": 1200,
        "USER_ACTUAL_NAME": 1105,
        "Origin": 1000,
        "Type": 1001,
        "Supply chain": 1002,
        "Coordinates": 1216
    }

    dfs = []

    for f in survey_files:
        df = pd.read_excel(f)
        df.columns = df.columns.astype(str).str.strip()
        df = df.rename(columns=mapping)
    
        if "1200" in df.columns:
            dfs.append(df)
    
    if not dfs:
        raise ValueError("No valid survey files with FARMER_CODE found")
    
    survey_resp = dfs[0]
    
    for df in dfs[1:]:
        survey_resp = pd.merge(
            survey_resp,
            df,
            on="FARMER_CODE",
            how="outer",
            suffixes=("", "_dup")
        )

    survey_resp = survey_resp.loc[:, ~survey_resp.columns.str.endswith("_dup")]

    survey_resp = survey_resp.loc[:, ~survey_resp.columns.str.endswith("_dup")]

    # normalize column names to leading digits where possible
    survey_resp.columns = [
        re.match(r"^\d+", str(c)).group(0) if re.match(r"^\d+", str(c)) else c
        for c in survey_resp.columns]

    survey_resp = survey_resp.loc[
        :, survey_resp.columns.astype(str).str.fullmatch(r"\d{4}")]

    reshape = survey_resp.melt(var_name="question", value_name="response")

    reshape["question"] = pd.to_numeric(reshape["question"], errors="coerce")
    qn_bank["qno"] = pd.to_numeric(qn_bank["qno"], errors="coerce")

    matched = qn_bank.merge(
        reshape,
        left_on="qno",
        right_on="question",
        how="left"
    )

    matched["record_id"] = matched.groupby("qno_q_group").cumcount()

    df = matched[["qno_q_group", "response", "record_id", "is_numerical"]].copy()
    
    mask = df["is_numerical"].fillna(False).astype(bool)

    df.loc[mask, "response"] = pd.to_numeric(df.loc[mask, "response"], errors="coerce")

    final = df.pivot(index="record_id", columns="qno_q_group", values="response")
    
    # 9. remove rows where all responses are missing (fully empty survey records)
    final = final.dropna(how='all')

    # final = final.fillna("")
    
    final = final.reset_index(drop=True)
    final.columns.name = None
    
    year_series = pd.to_datetime(final.get("1106_survey_date_completion"), errors="coerce").dt.year
    
    year_mode = year_series.mode()
    
    final["1003_survey_year"] = int(year_mode.iloc[0]) if not year_mode.empty else None
    
    final["1104_survey_person_manager"] = manager_name
    
    first_cols = final.columns[:4]
    
    final = final.dropna(subset=first_cols).reset_index(drop=True)
    
    # final.columns = final.columns.str.strip().str.replace("\u200b", "", regex=True)
    
    return final

# ---------------- HEADER ----------------
col_left, col_main, col_right = st.columns([2, 6, 2])

with col_main:
    c1, c2 = st.columns([1, 8])
    with c1:
        st.image("IMPACT_logo.png", width=60)
    with c2:
        st.title("IMPACT Progress Data Validation")

st.divider()

# ---------------- LEFT PANEL ----------------
with col_left:
    st.markdown("### 📘 About")
    st.write("""
    This tool standardizes IMPACT Progress survey data into a clean analytical dataset
    for reporting and dashboards.
    """)

    st.markdown("### ⚙️ What it does")
    st.write("""
    - Merges survey files  
    - Maps question bank  
    - Cleans and reshapes data  
    - Generates standardized output  
    """)

    st.markdown("### 📌 Tip")
    st.info("- Upload survey files from Roots\n- Ensure consistent `FARMER_CODE` across files")

# ---------------- MAIN PANEL ----------------
with col_main:

    survey_files = st.file_uploader(
        "Upload Survey Files:",
        type=["xlsx"],
        accept_multiple_files=True
    )

    manager = st.text_input("Enter Sustainability Manager / Coordinator:")

    # ---------------- FIXED PROCESSING LOGIC ----------------
    if survey_files and manager:

        file_names = [f.name for f in survey_files]
        current_signature = str(file_names) + "_" + manager

        if st.session_state.last_signature != current_signature:

            with st.spinner("Processing data..."):
                df = process_files(qn_bank, survey_files, manager)

            st.session_state.final = df
            st.session_state.processed = True
            st.session_state.last_signature = current_signature

    # ---------------- PREVIEW ----------------
    if st.session_state.final is not None:
        st.subheader("Standardized Data Preview")
        st.text(f"Records: {st.session_state.final.shape[0]}")
        st.dataframe(st.session_state.final)


# ---------------- RIGHT PANEL ----------------
with col_right:

    st.markdown("### 📊 System Status")

    if st.session_state.processed:
        st.success("Ready")
    else:
        st.warning("Waiting for processing")

    # ---------------- DATA TYPES ----------------
    if st.session_state.processed and st.session_state.final is not None:

        with st.expander("🧾 View Data Types", expanded=False):

            dtype_df = st.session_state.final.dtypes.reset_index()
            dtype_df.columns = ["column", "dtype"]

            st.dataframe(dtype_df, use_container_width=True)

    else:
        st.caption("Process data to enable inspection")

    # ---------------- DOWNLOAD ----------------
    if st.session_state.processed and st.session_state.final is not None:

        df = st.session_state.final

        st.markdown("### ⬇️ Download")

        file_type = st.selectbox(
            "Format",
            ["csv", "xlsx", "xls"],
            label_visibility="collapsed"
        )

        file_name = "survey_output"

        if file_type == "csv":

            st.download_button(
                "Download CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=file_name + ".csv",
                mime="text/csv"
            )

        elif file_type == "xlsx":

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="data")
            buffer.seek(0)

            st.download_button(
                "Download XLSX",
                data=buffer,
                file_name=file_name + ".xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="data")
            buffer.seek(0)

            st.download_button(
                "Download XLS",
                data=buffer,
                file_name=file_name + ".xls",
                mime="application/vnd.ms-excel"
            )


# ---------------- FOOTER ----------------
st.markdown(
    """
    <div style="text-align:center; color:gray; font-size:12px;">
        © 2026 IMPACT Progress Data Tool
    </div>
    """,
    unsafe_allow_html=True
)
