# Quality Rubric

1. Call create_xlsx for every spreadsheet request. Never answer with text only when the user asked for an Excel file.
2. Build the data completely BEFORE the call: first row = meaningful headers, then the values. Pass them as a JSON array of arrays.
3. Numbers stay numbers (no currency symbols in numeric cells - units in the header, e.g. "Revenue (EUR)").
4. For research answers: web_search first (if needed), then build the table from the evidenced numbers. Do not invent metrics.
5. Choose a descriptive, ASCII-safe filename with .xlsx.
6. Ground every number/path on real tool output; no simulated output without a returned path.
