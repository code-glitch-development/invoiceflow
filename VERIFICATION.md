# Validation

- Ten tests passed: seven business-rule tests and three localization tests covering translation templates, user data in exports and preservation of financing eligibility.
- Python compilation of the application and modules passed.
- Two Streamlit integration tests are included but were skipped because Streamlit is unavailable in the creation environment. They exercise both languages across all screens and switch languages after financing an invoice.
- No browser validation or live deployment was performed.

After installing dependencies, run `python -m unittest -v` from the project folder to execute the integration tests as well.
