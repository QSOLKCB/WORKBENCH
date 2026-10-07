# Getting started

From a source checkout, use Python 3.10 or newer:

```sh
python3 workbench.py --version
python3 workbench.py discover
python3 workbench.py run demo.experiment --params '{"steps":3,"seed":7,"delay":0}'
python3 workbench.py history
```

The explicitly labelled demo returns `total: 42`. It never replaces an unavailable backend.

Run `python3 workbench.py tui` in an interactive terminal with curses, or `python3 workbench.py web` and open the exact URL it prints. Ctrl+C stops the web session and cancels its owned jobs.

Optional connections are configured in a local JSON file; see [usage and backend setup](docs/USAGE.md). Keep private prompts and run stores out of the repository.

See [instructions](INSTRUCTIONS.md) for validation commands and [validation boundaries](docs/VALIDATION.md) before treating integration fixtures as real scientific or model evidence.
