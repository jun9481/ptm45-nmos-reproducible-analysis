# Final release verification checklist

- [x] Configuration contains `vgs_start_v = -0.2`
- [x] Generated-netlist logic uses the configured VGS start
- [x] Expected row count uses `(stop - start) / step + 1`
- [x] First point and VGS spacing have explicit checks
- [x] Bundled combined CSV contains 5 curves and 1,245 rows
- [x] All five curves start at −0.2 V with 5 mV spacing
- [x] Metrics contains 4 rows and `Ioff_definition_VGS_V = 0`
- [x] Latest summary, six figures, and Vth/DIBL CSV tables were regenerated
- [x] Python–Excel workbook reports 16/16 PASS
- [x] Sensitivity workbook reports PASS, 60/72 evaluable and no edge contacts
- [x] 728-window, 72-grid and 10-cutoff source CSVs reproduce from code
- [x] Model-card SHA-256 is enforced before simulator execution
- [x] Generated netlists contain repository-relative model paths
- [x] 36 unit, integration, bundled-result, sensitivity and release-integrity tests pass
- [x] Release manifest and semantic Ion/Ioff/SS/Vth/DIBL verifiers pass
- [x] Model cards, missing raw text and logs are disclosed rather than implied
- [x] ZIP archive integrity test passes
