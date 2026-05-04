"""Concrete DataSource implementations beyond the synthetic fixture path.

The DataSource interface itself stays in `datasource.py` (root). This package
holds adapters that read real-shaped data — starting with `CsvDataSource` for
bring-your-own-CRM-export use.
"""

from datasources.csv_source import CsvDataSource

__all__ = ["CsvDataSource"]
