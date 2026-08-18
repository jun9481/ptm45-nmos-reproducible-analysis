# PTM model cards

Place the two official files here without changing their names:

- `45nm_HP.pm` — expected SHA-256 `c9ed2e513523c57a76912a35b2860cb85e4aaa3402b69757d84efa9cc2fb8410`
- `45nm_LP.pm` — expected SHA-256 `397141eb8a813045075ac2be3098d3b136ebaf4d597c08fca627922a75e443b7`

Official landing page: <https://mec.umn.edu/ptm>

The files are intentionally not redistributed in this project. The pipeline
requires each downloaded file's SHA-256 to match `project_config.json` before
simulation and records the verified digest in the data manifest.
