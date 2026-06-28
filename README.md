# Arknights Recruitment Helper

A small Python desktop app that helps with Arknights recruitment.

It can:

- download EN game data from `ArknightsAssets/ArknightsGamedata`
- build the current recruitment operator pool from the recruitment details
- show possible operators for every tag combination
- take a screenshot and try to OCR visible recruitment tags
- fall back to manual tag selection when OCR is not configured

## Setup

Python 3.10+ is recommended.

```powershell
<python -m venv .venv
.\.venv\Scripts\Activate.ps1>
pip install -r requirements.txt
python -m arkrecruit
```

## OCR Notes

The app calls the Tesseract OCR program directly. Install Tesseract OCR on Windows and restart the app.

If OCR is not available, the app still works: select tags manually and click **Analyze Selected Tags**.

For better OCR results, click **Set Screen Region**, drag a rectangle around the recruitment tag area, then click **Scan Screen Tags**.
