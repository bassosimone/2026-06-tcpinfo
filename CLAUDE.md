# Assistant Notes

## Reference Documentation

Read [docs/tcpinfo_inventory_llm.txt](docs/tcpinfo_inventory_llm.txt)
before analyzing TCPInfo/BBRInfo data. It documents the meaning
of each variable, sampling classes (counter vs gauge), PEP/middlebox
considerations, and common interpretation pitfalls.

## Conventions

- Use `uv run` to run Python scripts (never `pip install`).

- Use `click` for CLI argument parsing in scripts. The Streamlit
  explorer uses `argparse` because Click's decorator model conflicts
  with Streamlit re-executing the script on every widget interaction.

- Use the `ruff` and `pyright` dev dependencies to vet the codebase.

- Scripts use `#!/usr/bin/env -S uv run` as shebang.

- The `GNUmakefile` orchestrates the pipeline.
