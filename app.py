import io
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Telegram Number Filter", page_icon="📱", layout="wide")

st.title("📱 Telegram Number Filter")
st.caption("Version 1 • India (+91) phone-number validation and reporting")

st.info(
    "This version validates phone-number formatting only. It does not check whether a number "
    "has a Telegram account. An unverified record means its Telegram status is unknown."
)

MAX_FILE_MB = 10
ALLOWED_EXTENSIONS = {"csv", "xlsx", "txt"}

def normalize_phone(value):
    """Return a normalized Indian phone number or a validation reason."""
    if pd.isna(value):
        return None, "Empty value"

    raw = str(value).strip()
    if not raw:
        return None, "Empty value"

    # Avoid treating numeric spreadsheet cells like 9.8765e+09 as phone strings.
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]

    # Keep a leading + if present; remove common visual separators.
    cleaned = re.sub(r"[\s().\-]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if not re.fullmatch(r"\+?\d+", cleaned):
        return None, "Contains unsupported characters"

    digits = cleaned[1:] if cleaned.startswith("+") else cleaned

    if cleaned.startswith("+"):
        if not digits.startswith("91"):
            return None, "Not an India (+91) number"
        national = digits[2:]
    elif digits.startswith("0091"):
        national = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        national = digits[2:]
    else:
        national = digits

    # Basic Indian mobile format check: 10 digits, first digit 6-9.
    if len(national) != 10:
        return None, "Indian mobile number must have 10 national digits"
    if national[0] not in "6789":
        return None, "Indian mobile number should start with 6, 7, 8, or 9"

    return "+91" + national, None

def read_upload(uploaded_file):
    ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
    raw = uploaded_file.getvalue()

    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds the {MAX_FILE_MB} MB limit.")

    if ext == "csv":
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    elif ext == "xlsx":
        df = pd.read_excel(io.BytesIO(raw), dtype=str, keep_default_na=False)
    elif ext == "txt":
        lines = raw.decode("utf-8-sig", errors="replace").splitlines()
        df = pd.DataFrame({"phone": lines})
    else:
        raise ValueError("Unsupported file type.")

    if df.empty:
        raise ValueError("The uploaded file has no rows.")

    return df

uploaded = st.file_uploader(
    "Upload a CSV, Excel (.xlsx), or TXT file (max 10 MB)",
    type=["csv", "xlsx", "txt"],
    help="For CSV/Excel, select the column that contains phone numbers. TXT should contain one number per line."
)

if uploaded:
    try:
        source_df = read_upload(uploaded)
    except Exception as exc:
        st.error(f"Could not read this file: {exc}")
        st.stop()

    st.subheader("Choose the phone-number column")
    columns = list(source_df.columns)
    default_idx = 0
    for i, col in enumerate(columns):
        if str(col).strip().lower() in {"phone", "phone_number", "mobile", "mobile_number", "number", "telephone"}:
            default_idx = i
            break

    phone_col = st.selectbox("Phone-number column", columns, index=default_idx)
    run = st.button("Validate and generate reports", type="primary")

    if run:
        rows = []
        first_seen = set()
        duplicate_numbers = set()

        for row_num, value in enumerate(source_df[phone_col].tolist(), start=2):
            normalized, error = normalize_phone(value)
            record = {
                "source_row": row_num,
                "original_value": str(value),
                "normalized_number": normalized or "",
                "validation_status": "Valid format" if normalized else "Invalid",
                "validation_note": error or "",
                "duplicate": False,
                "telegram_status": "Not checked"
            }

            if normalized:
                if normalized in first_seen:
                    record["duplicate"] = True
                    record["validation_status"] = "Duplicate"
                    duplicate_numbers.add(normalized)
                else:
                    first_seen.add(normalized)

            rows.append(record)

        result_df = pd.DataFrame(rows)
        valid_df = result_df[result_df["validation_status"] == "Valid format"].copy()
        invalid_df = result_df[result_df["validation_status"] == "Invalid"].copy()
        duplicate_df = result_df[result_df["duplicate"] == True].copy()
        unverified_df = result_df[result_df["normalized_number"] != ""].copy()
        unverified_df["telegram_status"] = "Unknown — not checked"

        summary = pd.DataFrame([
            {"Metric": "Original rows", "Count": len(result_df)},
            {"Metric": "Valid unique numbers", "Count": len(valid_df)},
            {"Metric": "Invalid rows", "Count": len(invalid_df)},
            {"Metric": "Duplicate rows", "Count": len(duplicate_df)},
            {"Metric": "Telegram status checked", "Count": 0},
            {"Metric": "Telegram status unknown", "Count": len(unverified_df)},
        ])

        st.session_state["result_df"] = result_df
        st.session_state["valid_df"] = valid_df
        st.session_state["invalid_df"] = invalid_df
        st.session_state["duplicate_df"] = duplicate_df
        st.session_state["unverified_df"] = unverified_df
        st.session_state["summary"] = summary
        st.session_state["processed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

if "result_df" in st.session_state:
    result_df = st.session_state["result_df"]
    valid_df = st.session_state["valid_df"]
    invalid_df = st.session_state["invalid_df"]
    duplicate_df = st.session_state["duplicate_df"]
    unverified_df = st.session_state["unverified_df"]
    summary = st.session_state["summary"]

    st.divider()
    st.subheader("Processing summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows processed", len(result_df))
    c2.metric("Valid unique", len(valid_df))
    c3.metric("Invalid", len(invalid_df))
    c4.metric("Duplicates", len(duplicate_df))
    st.caption(f"Processed at: {st.session_state['processed_at']}")

    tabs = st.tabs(["All records", "Valid", "Invalid", "Duplicates", "Unverified", "Daily summary"])
    with tabs[0]:
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(valid_df, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(invalid_df, use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(duplicate_df, use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(unverified_df, use_container_width=True, hide_index=True)
        st.caption("Unverified means Telegram account status was not checked; it does not mean no account exists.")
    with tabs[5]:
        st.dataframe(summary, use_container_width=True, hide_index=True)

    def csv_bytes(df):
        return df.to_csv(index=False).encode("utf-8-sig")

    st.subheader("Download reports")
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button("Download valid.csv", csv_bytes(valid_df), "valid.csv", "text/csv")
        st.download_button("Download invalid.csv", csv_bytes(invalid_df), "invalid.csv", "text/csv")
    with d2:
        st.download_button("Download duplicates.csv", csv_bytes(duplicate_df), "duplicates.csv", "text/csv")
        st.download_button("Download unverified.csv", csv_bytes(unverified_df), "unverified.csv", "text/csv")
    with d3:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            result_df.to_excel(writer, sheet_name="All Records", index=False)
            valid_df.to_excel(writer, sheet_name="Valid", index=False)
            invalid_df.to_excel(writer, sheet_name="Invalid", index=False)
            duplicate_df.to_excel(writer, sheet_name="Duplicates", index=False)
            unverified_df.to_excel(writer, sheet_name="Unverified", index=False)
            summary.to_excel(writer, sheet_name="Summary", index=False)
        st.download_button(
            "Download all reports.xlsx",
            excel_buffer.getvalue(),
            "telegram_number_filter_reports.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

st.divider()
st.caption("Privacy reminder: only upload numbers you are authorized to process. Results are held in the current app session; avoid using this app on shared computers.")
