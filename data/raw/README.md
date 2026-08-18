# Raw simulation output

`python ptm_pipeline.py simulate` writes ngspice `wrdata` tables here. Preserve
these files unchanged as the source for processed CSV files.

The five raw text files from the bundled 2026-08-15 result were not present in
the supplied extended-results archive. Their source-run hashes remain recorded
in `data/metadata/data_manifest.csv`; run the full pipeline to create new raw
files and logs in the local environment.
