# PlagCheck — Postman API Collection & Environment

This directory contains the ready-to-import Postman Collection and Environment files for testing and interacting with the **PlagCheck REST API**.

---

## 📁 Files Included

1. **`PlagCheck.postman_collection.json`**
   Contains all API endpoints grouped logically into folders (`System`, `Detection & Scans`, `Reports & Analysis`).
2. **`PlagCheck.postman_environment.json`**
   Environment configuration containing `base_url`, `scan_id`, `file_a`, and `file_b` variables.

---

## 🚀 How to Import & Use in Postman

### Step 1: Open Postman
Download and launch [Postman](https://www.postman.com/downloads/) desktop client or open Postman Web.

### Step 2: Import Files
1. In Postman, click the **Import** button (top-left).
2. Select or drag-and-drop both files:
   - `PlagCheck.postman_collection.json`
   - `PlagCheck.postman_environment.json`
3. Click **Import**.

### Step 3: Select the Environment
In the top-right environment dropdown selector in Postman, choose **`PlagCheck Local Environment`**.

---

## 📡 Endpoints Included

### 1. System
- **`GET /api/status`**: System health check.
- **`GET /api/modes`**: List supported scanning modes (`text_similarity`, `code_similarity`).
- **`GET /api/algorithms`**: List selectable algorithms per mode.

### 2. Detection & Scans
- **`POST /api/detect-language`**: Send code snippet to auto-detect language (Python, Java, C, C++).
- **`POST /api/check`**: Upload files (`multipart/form-data`) to run a plagiarism scan.
  > 💡 **Automation**: When you run a scan, a built-in Postman test script automatically extracts `scan_id`, `file_a`, and `file_b` from the response and saves them to your Postman Environment variables!

### 3. Reports & Analysis
- **`GET /api/report/{{scan_id}}`**: Fetch scan summary report & scores.
- **`GET /api/report/{{scan_id}}/pair/{{file_a}}/{{file_b}}`**: Retrieve detailed text comparison & highlight offsets for two files.
- **`GET /api/report/{{scan_id}}/heatmap.png`**: Download/View the 300 DPI similarity matrix heatmap PNG image.

---

## ⚡ Starting the Local API

Make sure your Flask API is running locally before sending requests:

```bash
# From the project root:
npm run api
# or
python plagcheck/app.py
```

The API will be available at `http://localhost:5000`.
