# Netlists

The pipeline creates one self-documenting `.cir` file per sweep under
`netlists/generated/`. Each generated file contains a repository-relative model
path, bias values, device dimensions, temperature, current-sign convention, and
raw output path used for that run.

Generate them with:

```bash
python ptm_pipeline.py generate-netlists
```
