# Test fixtures

## `turnuser_R26.pdf` (golden-file regression test)

`tests/test_data_integrity.py::TestScraperRoundtrip` re-scrapes the real R26
source PDF and asserts the output matches the committed
`app/static/turnusfiler/r26/turnus_schedule_R26.json` (names, count, `tid`,
`dagsverk`, totals, and `start`/`slutt`). This locks the scraper's behavior so
any future change — or the eventual switch to a structured data source — is
caught immediately.

To enable it, drop the source PDF here:

```
tests/fixtures/turnuser_R26.pdf
```

This path is **not** covered by the `.gitignore` rule
`app/static/turnusfiler/**/*.pdf`, so committing it keeps the regression test
runnable in CI. If the file is absent, the roundtrip tests `skip` (the rest of
the suite still runs).

The test also falls back to `app/static/turnusfiler/r26/pdf/turnuser_R26.pdf`
(where an admin upload writes it) if no fixture is committed here.
