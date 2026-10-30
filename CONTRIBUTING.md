# Contributing

Issues and pull requests are welcome.

- Run `just test` and, if you touched `bookmarkwise/extension_template/`, the real-browser test: `CHROMIUM=/path/to/chromium just e2e`.
- Run `just demo` if the output of any command changed, and commit `examples/walkthrough.txt`.
- Use invented data only: no real bookmarks in tests, examples or issues.
- Python stays stdlib-only (3.10+). The extension keeps the single `bookmarks` permission.
