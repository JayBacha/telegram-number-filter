# Telegram Number Filter — Version 1

## Features
- Upload CSV, XLSX, or TXT (TXT: one number per line)
- Choose the phone-number column
- Normalize and validate basic Indian mobile-number format (+91)
- Identify duplicate rows
- Export separate valid, invalid, duplicate, and unverified reports
- Export all reports into one Excel workbook

## Important limitation
This version does **not** check Telegram account existence. `Unverified` means the Telegram status is unknown and was not checked.

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run:
   ```bash
   python -m venv .venv
   ```
4. Activate the environment:
   - Windows: `.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`
5. Install packages:
   ```bash
   pip install -r requirements.txt
   ```
6. Start:
   ```bash
   streamlit run app.py
   ```
7. Open the local URL shown in the terminal.

## Input format
CSV/Excel: one column containing phone numbers. You can name it `phone`, `mobile`, `number`, or choose the correct column after upload.
TXT: one phone number per line.

## Notes
- Maximum upload size: 10 MB.
- Basic format validation is not a guarantee that a number is active or assigned.
- Do not upload third-party data unless you have a lawful basis and permission to process it.
