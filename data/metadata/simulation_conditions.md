# Simulation conditions for bundled v1.0 results

- Model source: Predictive Technology Model, University of Minnesota
- Data type: PTM model-based simulation; not measured silicon data
- Simulator observed in the successful source run: ngspice-46
- Device: NMOS
- W: 1 µm
- L: 0.045 µm (45 nm)
- Body and source: 0 V
- Temperature: 25 °C
- VGS start: −0.2 V
- VGS step: 0.005 V
- Ioff definition: VGS = 0 V

## Sweep inventory

| Application | Bias label | VDS (V) | VGS range (V) | Rows | Comparison basis |
|---|---|---:|---:|---:|---|
| HP | low_vds | 0.05 | −0.2 to 1.0 | 241 | low_drain_bias |
| HP | nominal_vdd | 1.0 | −0.2 to 1.0 | 241 | model_nominal_vdd |
| LP | low_vds | 0.05 | −0.2 to 1.1 | 261 | low_drain_bias |
| LP | nominal_vdd | 1.1 | −0.2 to 1.1 | 261 | model_nominal_vdd |
| LP | common_1v | 1.0 | −0.2 to 1.0 | 241 | common_vdd |

## Model identities

- HP SHA-256: `c9ed2e513523c57a76912a35b2860cb85e4aaa3402b69757d84efa9cc2fb8410`
- LP SHA-256: `397141eb8a813045075ac2be3098d3b136ebaf4d597c08fca627922a75e443b7`

The bundled `data_manifest.csv` also records the five source-run raw-file
hashes. The corresponding raw text files were not included in the supplied
extended-results archive and therefore are not present in this release.
