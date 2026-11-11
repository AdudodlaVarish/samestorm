# Same Storm, Different Answers

Use Python 3.14.7, recorded in `.python-version`. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python scripts/validate_dataset.py
python -m unittest discover -s tests -v
```

The validator and tests require no third-party packages; `requirements.txt`
records that scope.
