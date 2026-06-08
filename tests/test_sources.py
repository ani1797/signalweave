import pytest
from pathlib import Path
from signalweave.sources import InMemorySource, RestSource, SqlSource, CsvFileSource

def test_in_memory_source():
    src = InMemorySource("mem", {"A": {"id": "A", "val": 1}})
    assert src.fetch("A") == {"id": "A", "val": 1}
    assert "error" in src.fetch("B")

def test_rest_source():
    src = RestSource("rest", "url", {"A": {"id": "A", "val": 2}})
    assert src.fetch("A") == {"id": "A", "val": 2}
    assert "error" in src.fetch("B")

def test_sql_source():
    src = SqlSource("sql", "conn", "table", {"A": {"id": "A", "val": 3}})
    assert src.fetch("A") == {"id": "A", "val": 3}
    assert "error" in src.fetch("B")

def test_csv_file_source(tmp_path):
    # create dummy csv
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,val\nA,4\nC,5\n")
    
    src = CsvFileSource("csv", csv_file, "id")
    # numeric values parse optionally
    res = src.fetch("A")
    assert res["id"] == "A"
    assert res["val"] == 4.0
    
    assert "error" in src.fetch("B")
