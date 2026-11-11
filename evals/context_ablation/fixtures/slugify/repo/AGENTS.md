# House rules for this repository

- Code lives in `src/`; the tests are the contract and we do not edit them to fit code.
- Run the checks with `python -m pytest -q tests`.
- A slug never contains two dashes in a row: a run of separators becomes one dash.
- A leading or trailing dash is never part of a slug.
- Public helpers stay one line where a comprehension says it, otherwise a named function.
