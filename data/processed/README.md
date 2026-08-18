# Processed data

`python ptm_pipeline.py process` writes tidy HP, LP, and combined CSV files here.

The v1.0 release includes the extended-sweep result: five curves and 1,245 rows
from VGS = −0.2 V to the configured endpoint.

`ptm45_combined.csv` is the canonical analysis input. The HP/LP split files are
convenience exports from the source run; `analyze`, sensitivity reconstruction,
and release regression tests all read the canonical combined file.
