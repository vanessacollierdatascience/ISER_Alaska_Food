# ISER Alaska Food Price Pipeline
### Institute for Social and Economic Research (ISER)
### University of Alaska Anchorage

---

## Overview

An end-to-end automated data collection, cleaning, and validation 
pipeline built to support cost-of-living research across Alaska. 
This pipeline collects grocery price data from major food retailers 
operating in Alaska, enabling economic research on food access and 
affordability that was previously unavailable at this scale.

This work contributed to ISER's cost-of-living research portfolio 
and supported policy-relevant analysis of food pricing disparities 
across urban and rural Alaska communities.

---

## What This Pipeline Does

### Data Collection
Automated scrapers collect current grocery price data from 
multiple major Alaska retailers:

| Script | Retailer | Notes |
|---|---|---|
| ACC_PULL_CURRENT.py | Alaska Commercial Company | Specializes in remote Bush communities |
| CS_PULL_CURRENT.py | Carrs/Safeway | Major urban Alaska grocery chain |
| FM_PULL_CURRENT.py | Fred Meyer | Pacific Northwest regional retailer |
| WM_PULL_CURRENT.py | Walmart | National retailer, urban Alaska locations |
| central_food_pull.py | All retailers | Aggregation and standardization pipeline |

### Pipeline Orchestration
Runner scripts coordinate automated execution across retailers:
- `acc_runner.py` — Alaska Commercial Company pipeline runner
- `central_runner.py` — Master pipeline orchestrator
- `cs_runner.py` — Carrs/Safeway pipeline runner

### Data Collection Methods
The pipeline supports multiple collection strategies:
- Automated web scraping for real-time price data
- Snapshot downloads for point-in-time comparisons
- Manual download imports for retailers with restricted access

### Data Cleaning & Validation
`Food_Data_Cleaning_Pipeline_Policy.py` implements:
- Automated data integrity checks
- Standardization across retailer-specific formats
- Quality validation for recurring data pulls
- Consistent product matching across stores

### Specialized Reporting
`Nome_Report_Script.py` generates reports specific to Nome, AK — 
a remote community with distinct food access challenges and 
pricing patterns.

---

## Research Context

Alaska presents unique food pricing challenges:
- Remote communities face significant supply chain costs
- Price disparities between urban and rural areas are substantial
- No comprehensive statewide food price dataset previously existed

This pipeline enabled cost-of-living research at a scale and 
geographic breadth previously unavailable, providing empirical 
data to support evidence-based policy decisions around food 
access and affordability in Alaska.

---

## Technical Stack

- **Language:** Python (92.6%) · R
- **Collection:** Automated web scraping · API integration · 
  Scheduled workflows
- **Processing:** Automated cleaning · Cross-retailer 
  standardization · QA validation
- **Output:** Structured datasets for statistical analysis 
  and policy reporting

---

## Data Access Note

This pipeline was developed for use with data infrastructure 
at the University of Alaska Anchorage. Raw price data is not 
included in this repository due to institutional data governance 
policies. The code demonstrates pipeline architecture, collection 
methodology, cleaning logic, and QA validation approach.

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
