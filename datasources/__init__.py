"""Concrete DataSource implementations beyond the synthetic fixture path.

The DataSource interface itself stays in `datasource.py` (root). This package
holds adapters that read real-shaped data — `CsvDataSource` for bring-your-own
CSV use, and `SalesforceDataSource` for live Salesforce orgs.
"""

from datasources.csv_source import CsvDataSource
from datasources.salesforce_source import SalesforceDataSource

__all__ = ["CsvDataSource", "SalesforceDataSource"]
