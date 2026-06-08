"""
Life Insurance Underwriting loaders demonstrating heterogeneous data sources.
"""
from typing import Any
from pathlib import Path
from agent_framework import tool

from ..sources import InMemorySource, RestSource, SqlSource, CsvFileSource

# 1. In-Memory Source (Application)
_APPLICATIONS = {
    "APP-1001": {"app_id": "APP-1001", "coverage_amount": 250000.0, "medical_id": "MED-1001", "lab_id": "LAB-1001", "rate_class": "preferred", "signature_present": True},
    "APP-2002": {"app_id": "APP-2002", "coverage_amount": 3000000.0, "medical_id": "MED-2002", "lab_id": "LAB-2002", "rate_class": "standard", "signature_present": True},
    "APP-3003": {"app_id": "APP-3003", "coverage_amount": 750000.0, "medical_id": "MED-3003", "lab_id": "LAB-3003", "rate_class": "substandard", "signature_present": False},
}
app_source = InMemorySource("Application Intake", _APPLICATIONS)

@tool
def load_application(app_id: str) -> dict[str, Any]:
    """Load the initial application data (InMemory Source).
    Returns the application details which include identifiers to fetch other reports.
    """
    res = app_source.fetch(app_id)
    if "error" in res: return res
    return {"application": res}


# 2. REST API Source (Medical Bureau)
_MEDICAL_RESPONSES = {
    "MED-1001": {"id": "MED-1001", "history_flag": False, "bmi": 24.5},
    "MED-2002": {"id": "MED-2002", "history_flag": False, "bmi": 26.1},
    "MED-3003": {"id": "MED-3003", "history_flag": True, "bmi": 32.0},
}
medical_source = RestSource("Medical Bureau API", "https://api.medbureau.example.com/v1/reports", _MEDICAL_RESPONSES)

@tool
def load_medical_report(medical_id: str) -> dict[str, Any]:
    """Load the medical history report via simulated REST API."""
    res = medical_source.fetch(medical_id)
    if "error" in res: return res
    return {"medical": res}


# 3. SQL DB Source (Lab Results)
_LAB_ROWS = {
    "LAB-1001": {"lab_id": "LAB-1001", "cholesterol": 180.0, "a1c": 5.2, "nicotine_positive": False},
    "LAB-2002": {"lab_id": "LAB-2002", "cholesterol": 240.0, "a1c": 6.8, "nicotine_positive": False},
    "LAB-3003": {"lab_id": "LAB-3003", "cholesterol": 280.0, "a1c": 7.5, "nicotine_positive": True},
}
lab_source = SqlSource("Lab Results Database", "postgres://user:pass@db:5432/labs", "lab_results", _LAB_ROWS)

@tool
def load_lab_results(lab_id: str) -> dict[str, Any]:
    """Load laboratory test results via simulated SQL Database query."""
    res = lab_source.fetch(lab_id)
    if "error" in res: return res
    return {"labs": res}


# 4. File CSV Source (Underwriting Rates)
rates_csv_path = Path(__file__).parent.parent / "sources" / "data" / "underwriting_rates.csv"
rates_source = CsvFileSource("Underwriting Rate File", rates_csv_path, "rate_class")

@tool
def load_rate_class(rate_class: str) -> dict[str, Any]:
    """Load rate class limits and multipliers via simulated File (CSV)."""
    res = rates_source.fetch(rate_class)
    if "error" in res: return res
    return {"rates": res}

