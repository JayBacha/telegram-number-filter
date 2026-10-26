import os, textwrap, zipfile

base = "/mnt/data/telegram_number_filter_v2"
os.makedirs(base, exist_ok=True)

app_code = r'''
import io
import re
from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Telegram Number Filter V2", page_icon="📱", layout="wide")

st.title("📱 Telegram Number Filter — Version 2")
st.caption("Phone validation • Authorized status-data matching • Last-seen filters • CSV/XLSX reports")

st.warning(
    "This app does not query Telegram or discover accounts from phone numbers. "
    "It can match numbers against a status file you are authorized to use. "
    "Missing status data is shown as Unknown, not as 'no Telegram account'."
)

MAX_FILE_MB = 10
SUPPORTED = ["csv", "xlsx", "txt"]

def normalize_phone(value):
    if pd.isna(value):
        return None, "Empty value"
    raw = str(value).strip()
    if not raw:
        return None, "Empty value"
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]
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
    elif digits.startswith("91") and len(digits) == 12:
        national = digits[2:]
    else:
        national = digits
    if len(national) != 10:
        return None, "Indian mobile number must have 10 national digits"
    if national[0] not in "6789":
        return None, "Indian mobile number should start with 6, 7, 8, or 9"
    return "+91" + national, None

def read_file(upload, max_mb=MAX_FILE_MB):
    raw = upload.getvalue()
    if len(raw) > max_mb * 1024 * 1024:
        raise ValueError(f"File exceeds {max_mb} MB.")
    ext = upload.name.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    elif ext == "xlsx":
        df = pd.read_excel(io.BytesIO(raw), dtype=str, keep_default_na=False)
    elif ext == "txt":
        df = pd.DataFrame({"phone": raw.decode("utf-8-sig", errors="replace").splitlines()})
    else:
        raise ValueError("Unsupported file type.")
    if df.empty:
        raise ValueError("File has no rows.")
    return df

def find_col(columns, candidates, fallback=0):
    for i, col in enumerate(columns):
        if str(col).strip().lower().replace(" ", "_") in candidates:
            return i
    return fallback

def parse_last_seen(value, now):
    """Return (UTC datetime or None, approximate label, parse note)."""
    if pd.isna(value) or not str(value).strip():
        return None, "", "No last-seen value"
    raw = str(value).strip()
    low = raw.lower()

    # Approximate Telegram-style labels are deliberately not converted to exact timestamps.
    approx = {
        "recently": "Approximate: recently",
        "last seen recently": "Approximate: recently",
        "within a week": "Approximate: within a week",
        "last seen within a week": "Approximate: within a week",
        "within a month": "Approximate: within a month",
        "last seen within a month": "Approximate: within a month",
        "a long time ago": "Approximate: a long time ago",
        "last seen a long time ago": "Approximate: a long time ago",
        "hidden": "Hidden / unavailable",
        "private": "Hidden / unavailable",
        "unavailable": "Hidden / unavailable",
    }
    if low in approx:
        return None, approx[low], "Approximate or hidden status; cannot apply exact-day filter"

    # Parse a timestamp; assume UTC if timezone is not specified.
    try:
        ts = pd.to_datetime(raw, utc=True, errors="raise")
        if pd.isna(ts):
            raise ValueError("No timestamp")
        return ts.to_pydatetime(), "", ""
    except Exception:
        return None, "", "Unrecognized last-seen format"

def to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

st.header("1. Upload phone-number list")
numbers_file = st.file_uploader(
    "Main list (CSV, XLSX, or TXT; max 10 MB)",
    type=SUPPORTED,
    key="numbers_file",
    help="TXT: one number per line. CSV/XLSX: choose the number column below."
)

if numbers_file:
    try:
        source_df = read_file(numbers_file)
    except Exception as e:
        st.error(f"Could not read the number file: {e}")
        st.stop()

    phone_col = st.selectbox(
        "Phone-number column",
        source_df.columns.tolist(),
        index=find_col(source_df.columns, {"phone", "phone_number", "mobile", "mobile_number", "number", "telephone"}),
        key="main_phone_col"
    )

    st.header("2. Optional: import authorized status data")
    st.caption(
        "Upload a separate CSV/XLSX containing phone numbers and status fields from a source you are permitted to use. "
        "Expected fields: phone, telegram_status (e.g. Active / No confirmed account / Unknown), "
        "and optionally last_seen (ISO timestamp or approximate label)."
    )
    status_file = st.file_uploader(
        "Authorized status data (optional CSV/XLSX; max 10 MB)",
        type=["csv", "xlsx"],
        key="status_file"
    )

    status_df = None
    status_phone_col = status_col = last_seen_col = None
    if status_file:
        try:
            status_df = read_file(status_file)
            status_columns = status_df.columns.tolist()
            status_phone_col = st.selectbox(
                "Status file: phone-number column",
                status_columns,
                index=find_col(status_columns, {"phone", "phone_number", "mobile", "mobile_number", "number", "telephone"}),
                key="status_phone_col"
            )
            status_col = st.selectbox(
                "Status file: account-status column",
                status_columns,
                index=find_col(status_columns, {"telegram_status", "account_status", "status"}, min(0, len(status_columns)-1)),
                key="status_col"
            )
            last_seen_options = ["(none)"] + status_columns
            last_seen_idx = 0
            for i, c in enumerate(status_columns, start=1):
                if str(c).strip().lower().replace(" ", "_") in {"last_seen", "last_seen_at", "last_seen_date", "last_active"}:
                    last_seen_idx = i
                    break
            last_seen_choice = st.selectbox(
                "Status file: last-seen column (optional)",
                last_seen_options,
                index=last_seen_idx,
                key="last_seen_col"
            )
            last_seen_col = None if last_seen_choice == "(none)" else last_seen_choice
        except Exception as e:
            st.error(f"Could not read the status file: {e}")
            st.stop()

    if st.button("Process and generate reports", type="primary"):
        now = datetime.now(timezone.utc)
        rows = []
        seen = set()
        status_lookup = {}

        if status_df is not None:
            for _, srow in status_df.iterrows():
                normalized, err = normalize_phone(srow[status_phone_col])
                if not normalized:
                    continue
                status_value = str(srow[status_col]).strip() or "Unknown"
                last_seen_value = str(srow[last_seen_col]).strip() if last_seen_col else ""
                last_seen_dt, approx_label, last_seen_note = parse_last_seen(last_seen_value, now) if last_seen_value else (None, "", "No last-seen value")
                # Keep first matching status record to avoid silently merging conflicting records.
                if normalized not in status_lookup:
                    status_lookup[normalized] = {
                        "telegram_status_source": status_value,
                        "last_seen_raw": last_seen_value,
                        "last_seen_utc": last_seen_dt.isoformat() if last_seen_dt else "",
                        "last_seen_category": approx_label,
                        "last_seen_note": last_seen_note
                    }

        for row_num, value in enumerate(source_df[phone_col].tolist(), start=2):
            normalized, error = normalize_phone(value)
            duplicate = bool(normalized and normalized in seen)
            if normalized and not duplicate:
                seen.add(normalized)

            status_info = status_lookup.get(normalized, {}) if normalized else {}
            raw_status = status_info.get("telegram_status_source", "")
            low_status = raw_status.strip().lower()

            if not normalized:
                account_status = "Invalid number"
            elif not status_file:
                account_status = "Unknown — no status data imported"
            elif not raw_status:
                account_status = "Unknown — no matching status record"
            elif low_status in {"active", "exists", "account exists", "telegram account exists", "confirmed"}:
                account_status = "Active / confirmed in supplied data"
            elif low_status in {"no account", "not found", "no telegram", "no telegram account", "not registered", "inactive"}:
                account_status = "No account indicated by supplied data"
            else:
                account_status = "Unknown — status not recognized"

            seen_iso = status_info.get("last_seen_utc", "")
            seen_dt = None
            if seen_iso:
                try:
                    seen_dt = pd.to_datetime(seen_iso, utc=True).to_pydatetime()
                except Exception:
                    seen_dt = None

            if not normalized:
                last_seen_bucket = "Not applicable"
            elif not status_file or not status_info:
                last_seen_bucket = "Unknown"
            elif status_info.get("last_seen_category"):
                last_seen_bucket = status_info["last_seen_category"]
            elif seen_dt is None:
                last_seen_bucket = "Unknown / unavailable"
            else:
                age = now - seen_dt
                if age < timedelta(0):
                    last_seen_bucket = "Timestamp in future"
                elif age <= timedelta(hours=24):
                    last_seen_bucket = "Within 24 hours"
                elif age <= timedelta(days=3):
                    last_seen_bucket = "Within 3 days"
                elif age <= timedelta(days=7):
                    last_seen_bucket = "Within 7 days"
                else:
                    last_seen_bucket = "More than 7 days"

            rows.append({
                "source_row": row_num,
                "original_value": str(value),
                "normalized_number": normalized or "",
                "validation_status": "Valid format" if normalized else "Invalid",
                "validation_note": error or "",
                "duplicate": duplicate,
                "telegram_status": account_status,
                "source_status_value": raw_status,
                "last_seen_raw": status_info.get("last_seen_raw", ""),
                "last_seen_utc": seen_iso,
                "last_seen_bucket": last_seen_bucket,
                "last_seen_note": status_info.get("last_seen_note", "")
            })

        result_df = pd.DataFrame(rows)
        valid_df = result_df[(result_df["validation_status"] == "Valid format") & (~result_df["duplicate"])].copy()
        invalid_df = result_df[result_df["validation_status"] == "Invalid"].copy()
        duplicate_df = result_df[result_df["duplicate"]].copy()
        active_df = result_df[result_df["telegram_status"] == "Active / confirmed in supplied data"].copy()
        no_account_df = result_df[result_df["telegram_status"] == "No account indicated by supplied data"].copy()
        unknown_df = result_df[result_df["telegram_status"].str.startswith("Unknown")].copy()

        summary = pd.DataFrame([
            {"Metric": "Rows processed", "Count": len(result_df)},
            {"Metric": "Valid unique numbers", "Count": len(valid_df)},
            {"Metric": "Invalid rows", "Count": len(invalid_df)},
            {"Metric": "Duplicate rows", "Count": len(duplicate_df)},
            {"Metric": "Active / confirmed in supplied data", "Count": len(active_df)},
            {"Metric": "No account indicated by supplied data", "Count": len(no_account_df)},
            {"Metric": "Unknown / not verified", "Count": len(unknown_df)},
            {"Metric": "Last seen within 24 hours", "Count": int((result_df["last_seen_bucket"] == "Within 24 hours").sum())},
            {"Metric": "Last seen within 3 days", "Count": int(result_df["last_seen_bucket"].isin(["Within 24 hours", "Within 3 days"]).sum())},
            {"Metric": "Last seen within 7 days", "Count": int(result_df["last_seen_bucket"].isin(["Within 24 hours", "Within 3 days", "Within 7 days"]).sum())},
        ])

        st.session_state["v2_result"] = {
            "all": result_df, "valid": valid_df, "invalid": invalid_df, "duplicates": duplicate_df,
            "active": active_df, "no_account": no_account_df, "unknown": unknown_df, "summary": summary,
            "processed_at": now.strftime("%Y-%m-%d %H:%M UTC")
        }

if "v2_result" in st.session_state:
    data = st.session_state["v2_result"]
    all_df = data["all"]
    st.divider()
    st.header("3. Results and filters")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows processed", len(all_df))
    m2.metric("Valid unique", len(data["valid"]))
    m3.metric("Active / confirmed", len(data["active"]))
    m4.metric("Unknown", len(data["unknown"]))
    st.caption(f"Processed at: {data['processed_at']}")

    status_options = sorted(all_df["telegram_status"].dropna().unique().tolist())
    chosen_status = st.multiselect("Filter by Telegram status", status_options, default=status_options)
    last_seen_options = sorted(all_df["last_seen_bucket"].dropna().unique().tolist())
    chosen_seen = st.multiselect("Filter by last seen", last_seen_options, default=last_seen_options)
    filtered = all_df[
        all_df["telegram_status"].isin(chosen_status) &
        all_df["last_seen_bucket"].isin(chosen_seen)
    ].copy()

    st.subheader(f"Filtered records ({len(filtered)})")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    tabs = st.tabs(["All", "Active / confirmed", "No account indicated", "Unknown", "Invalid", "Duplicates", "Summary"])
    tab_frames = [all_df, data["active"], data["no_account"], data["unknown"], data["invalid"], data["duplicates"], data["summary"]]
    for tab, frame in zip(tabs, tab_frames):
        with tab:
            st.dataframe(frame, use_container_width=True, hide_index=True)

    st.subheader("4. Download reports")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("Download filtered.csv", to_csv_bytes(filtered), "filtered.csv", "text/csv")
        st.download_button("Download active_confirmed.csv", to_csv_bytes(data["active"]), "active_confirmed.csv", "text/csv")
    with col2:
        st.download_button("Download no_account_indicated.csv", to_csv_bytes(data["no_account"]), "no_account_indicated.csv", "text/csv")
        st.download_button("Download unknown.csv", to_csv_bytes(data["unknown"]), "unknown.csv", "text/csv")
    with col3:
        st.download_button("Download invalid.csv", to_csv_bytes(data["invalid"]), "invalid.csv", "text/csv")
        st.download_button("Download duplicates.csv", to_csv_bytes(data["duplicates"]), "duplicates.csv", "text/csv")
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            all_df.to_excel(writer, sheet_name="All Records", index=False)
            filtered.to_excel(writer, sheet_name="Filtered", index=False)
            data["active"].to_excel(writer, sheet_name="Active Confirmed", index=False)
            data["no_account"].to_excel(writer, sheet_name="No Account Indicated", index=False)
            data["unknown"].to_excel(writer, sheet_name="Unknown", index=False)
            data["invalid"].to_excel(writer, sheet_name="Invalid", index=False)
            data["duplicates"].to_excel(writer, sheet_name="Duplicates", index=False)
            data["summary"].to_excel(writer, sheet_name="Summary", index=False)
        st.download_button(
            "Download all_reports.xlsx",
            excel_buffer.getvalue(),
            "telegram_number_filter_v2_reports.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

st.divider()
st.caption(
    "Privacy: process only data you are authorized to use. Do not treat supplied status labels as independently verified facts. "
    "Approximate labels such as 'recently' are kept approximate and are not assigned an exact 24-hour/3-day/7-day window."
)
'''
requirements = """streamlit>=1.36
pandas>=2.0
openpyxl>=3.1
"""
readme = r'''
# Telegram Number Filter V2

## What it does
- Upload a phone-number list as CSV, XLSX, or TXT.
- Normalize and validate basic Indian mobile number formatting (+91).
- Detect duplicates.
- Optionally upload a separate authorized CSV/XLSX containing phone numbers, `telegram_status`, and optional `last_seen` data.
- Match authorized status data to numbers.
- Filter/export active/confirmed, no-account-indicated, unknown, invalid, duplicate, and last-seen buckets.
- Export a combined Excel workbook.

## Important limitation
This app does not query Telegram, discover accounts from phone numbers, or retrieve last-seen information. It matches the main list against a status file that you are authorized to use. Status values are not independently verified by this app. Missing or ambiguous records remain `Unknown`.

## Status file example
Create a CSV or Excel file with columns like:

| phone | telegram_status | last_seen |
|---|---|---|
| +919876543210 | Active | 2026-10-26T15:30:00Z |
| 9876543211 | Unknown | recently |
| +919876543212 | No account | |

Accepted status values:
- Active/confirmed: `Active`, `exists`, `account exists`, `confirmed`
- No account indicated: `No account`, `not found`, `no telegram`, `not registered`, `inactive`
- Any other value is classified as Unknown.

`last_seen` accepts a timestamp parseable by pandas, ideally ISO 8601 with timezone, e.g. `2026-10-26T15:30:00Z`. Approximate labels such as `recently`, `within a week`, `within a month`, `a long time ago`, `hidden`, and `private` remain approximate and cannot be assigned to exact 24-hour/3-day/7-day buckets.

## Deploy on Streamlit Community Cloud
1. Extract this ZIP on your computer.
2. Create a GitHub repository, e.g. `telegram-number-filter-v2`.
3. Upload `app.py` and `requirements.txt` (README optional) to the repository root, not inside another nested folder.
4. Open https://share.streamlit.io/ and sign in with GitHub.
5. Create app, select your repository, branch `main`, and main file `app.py`.
6. Deploy.

No local Python installation is required to deploy through the browser. Keep repositories free of real phone-number data. The app does not include authentication or permanent database storage; do not publish sensitive records in a public repository or use the public app for confidential lists.
'''
for name, content in [("app.py", app_code), ("requirements.txt", requirements), ("README.md", readme.strip()+"\n")]:
    with open(os.path.join(base, name), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content).strip()+"\n")
zip_path="/mnt/data/telegram_number_filter_v2.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
    for name in ["app.py","requirements.txt","README.md"]:
        z.write(os.path.join(base,name),arcname=f"telegram_number_filter_v2/{name}")
print("Created Version 2 package:", zip_path)
