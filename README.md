# ISER Alaska Food Price Pipeline
### Institute for Social and Economic Research (ISER)
### University of Alaska Anchorage

---

## Overview

An end-to-end automated data collection, cleaning, validation, 
and assembly pipeline built to support cost-of-living research 
across Alaska. This pipeline collects grocery price data from 
major food retailers operating in Alaska — including retailers 
serving remote Bush communities — enabling economic research on 
food access and affordability previously unavailable at this scale.

This work contributed to ISER's cost-of-living research portfolio 
and supported policy-relevant analysis of food pricing disparities 
across urban and rural Alaska communities.

---

## Pipeline Architecture

This is a fully productionized research data pipeline with 
modular components for collection, assembly, validation, 
and reporting.

### 1. Data Collection — Retailer Scrapers

Automated scrapers collect current grocery price data from 
multiple major Alaska retailers:

| Script | Retailer | Notes |
|---|---|---|
| ACC_PULL_CURRENT.py | Alaska Commercial Company | Specializes in remote Bush communities |
| CS_PULL_CURRENT.py | Carrs/Safeway | Major urban Alaska grocery chain |
| FM_PULL_CURRENT.py | Fred Meyer | Pacific Northwest regional retailer |
| WM_PULL_CURRENT.py | Walmart | National retailer, urban Alaska locations |
| central_food_pull.py | All retailers | Aggregation and standardization pipeline |

Multiple collection methods supported:
- Automated web scraping for real-time price data
- Snapshot downloads for point-in-time comparisons
- Manual download imports for restricted-access retailers

### 2. Pipeline Orchestration — Runners

Dedicated runner scripts coordinate automated execution 
per retailer:

| Script | Function |
|---|---|
| acc_runner.py | Alaska Commercial Company runner |
| cs_runner.py | Carrs/Safeway runner |
| fm_runner.py | Fred Meyer runner |
| wm_runner.py | Walmart runner |
| central_runner.py | Master pipeline orchestrator |

### 3. Master Assembly

`master_assembly.py` aggregates outputs from all retailer 
pipelines into a unified dataset. `master_assembly_bat.bat` 
enables scheduled Windows batch execution for automated 
recurring runs.

### 4. Schema & Validation

- `schema.py` — defines and enforces consistent data structure 
  across all retailer sources
- `master_qa.py` — dedicated quality assurance module with 
  automated integrity checks
- `prebuild_missing_store_months.py` — identifies and handles 
  gaps in store coverage across time periods
- `raw_discovery.py` — raw data exploration and anomaly detection

### 5. Batch Automation & Logging

- `run_food_pull.bat` — Windows batch script for scheduled 
  automated execution
- `pipeline_log.txt` — running pipeline execution log
- `pipeline_run_20251231_173711.txt` — point-in-time run record
- `run_food_pull_master.log` — master execution log
- `ACC_20251115.log` / `central_20251217_140221.log` — 
  retailer-specific run logs

### 6. Specialized Reporting

`Nome_Report_Script.py` generates reports specific to Nome, AK —
a remote community with distinct food access challenges and 
significant pricing disparities relative to urban Alaska.

---

## Research Context

Alaska presents unique food pricing challenges:
- Remote Bush communities face substantial supply chain costs
- Price disparities between urban and rural areas are extreme
- No comprehensive statewide food price dataset previously existed

This pipeline enabled cost-of-living research at a scale and 
geographic breadth previously unavailable, providing empirical 
data to support evidence-based policy decisions around food 
access and affordability in Alaska.

---

## Technical Stack

- **Languages:** Python 96% · Batchfile 4%
- **Collection:** Automated web scraping · Snapshot downloads · 
  Manual import handling
- **Processing:** Schema validation · Cross-retailer 
  standardization · Automated QA · Gap detection
- **Automation:** Windows batch scheduling · Execution logging
- **Dependencies:** See requirements.txt
- **Output:** Structured datasets for statistical analysis 
  and policy reporting

---

## Documentation

- `Food_Data_Cleaning_Pipeline_Policy.py` — cleaning 
  policy documentation
- `Revised Food Retail Data Pipeline.py` — updated pipeline 
  architecture documentation
- `WM_search_list.txt` — Walmart product search term list
- `wm_snapshot_registry.csv` — registry tracking Walmart 
  snapshot collection history across time periods

---

## Data Access Note

This pipeline was developed for use with data infrastructure 
at the University of Alaska Anchorage. Raw price data is not 
included in this repository due to institutional data governance 
policies. The code demonstrates pipeline architecture, collection 
methodology, schema validation, QA logic, and batch automation 
approach.

To adapt for your environment, update file paths and 
retailer credentials in the configuration files.

---

## Author

**Vanessa Collier**  
Research Professional III — Data Analyst / Analytics Engineer  
Institute for Social and Economic Research (ISER)  
University of Alaska Anchorage · 2022–2025  

[GitHub](https://github.com/vanessacollierdatascience) · 
[data-alchemy.studio](https://data-alchemy.studio)
