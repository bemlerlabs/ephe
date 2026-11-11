# House rules for this repository

- Money lives in integer cents end to end; a float never touches a price.
- Weekend surcharges are rounded up to the next whole cent.
- Saturday carries fifteen percent, Sunday five percent, every other day nothing.
- Run the checks with `python -m pytest -q tests`; the tests are the contract.
