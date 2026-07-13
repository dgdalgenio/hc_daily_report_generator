# MSME Client Survey & SA Performance Report Generator

An interactive Streamlit web application designed to automate the parsing, processing, and generation of daily operational metrics and Month-to-Date (MTD) insights for MSME client surveys. 

---

## Features

* **File Upload Integration:** Directly process raw `MSME Client Survey Form` Excel files via drag-and-drop.
* **Interactive Parameters:** Select custom report dates dynamically via an on-screen calendar interface.
* **Dynamic DSS & Email Mapping:** Edit Assigned Sales Director/DSS names and emails on the fly inside the application sidebar before compilation.
* **Automated Data Visualizations:** Generates a stacked bar and trend line chart mapping city-wide loan interest volumes and rates.
* **Live Report Preview:** View a live preview of the final `email_ready.html` report within your browser before saving.
* **Instant Export:** Generates an optimized, standalone HTML asset containing embedded base64 graphics for a plug-and-play email dispatch.
---
# Link to app
https://msmedailyreportgenerator.streamlit.app/

## How to use
1. Upload the updated MSME Client Survey Form in the top part of the left sidebar.
2. Select the date of the report. By default, this displays the previous date.
3. Add your sign-off name (optional).
4. Use your preferred AI model for insights generation. Input the API Key, if necessary. 
5. Check, and update if needed, the DSS and Email Assignments. This will impact the in the per-city pivot tables.
6. Click 'Process Data and Compile Report'
7. Once the report is finished, you may copy and paste the output from the app, or download the `email_ready.html` file.