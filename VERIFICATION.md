# Validation

- Seventeen automated tests passed: nine engine tests, three localization tests and five SQLite persistence tests.
- Coverage includes detailed eligibility reasons, completing invoice checks, historical progress after financing, reopening saved data, cross-session duplicate prevention, optimistic concurrency, atomic reset and error handling.
- Python compilation of all modules passed.
- Three Streamlit integration tests are provided but skipped because Streamlit is unavailable in the creation environment. They cover both languages, all seven pages, guided navigation, language switching and persistence after reopening the application.
- No browser validation or live deployment was performed.
- SQLite preserves records while its file is retained. Durable storage across Streamlit Community Cloud restarts/redeployments is not configured; see README for the persistent-disk deployment option and hosting limitations.

After installing dependencies, run `python -m unittest -v` from the project folder to execute the integration tests as well.
