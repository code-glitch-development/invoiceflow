# InvoiceFlow ↗

An English-language Streamlit demo for invoice financing and reverse factoring, based on the supplied InvoiceFlow concept. All companies and transactions are fictional. No money is transferred.

## Run locally

Requires Python 3.10 or later. Open a terminal in the project folder:

```bash
python -m venv .venv
```

Activate the environment:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- macOS / Linux: `source .venv/bin/activate`

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the address shown in the terminal, usually http://localhost:8501. No API key is required.

## Three-minute demo

1. Open **Overview** to explore the four fictional examples.
2. Select **SME → Upload an invoice**. Enter a new invoice reference, a fictional 9-digit SIREN, an amount and a future due date. Select **Strong** and **On time**, and tick both simulated checks.
3. Select **Buyer → Buyer confirmation**. Choose the buyer and invoice, check the confirmation box and save. You can also dispute an invoice with a reason.
4. Select **Investor → Financing**. Choose the confirmed invoice, adjust the fee, recourse and hypothetical coverage, then simulate financing.
5. Open **Portfolio** to export CSV or JSON, and simulate late payment, a dispute, insolvency or full payment.
6. Use **Simulator** independently to explore advances, losses and hypothetical monthly and annual fee revenue.

Use the sidebar to reset the demo. Example due dates are relative to the current date.

## Model and limitations

- Roles are freely interchangeable for presentation purposes: there is no authentication or access control.
- Data lives in `st.session_state`, without a database or sharing across browsers. Ending or reconnecting a session may lose the data. JSON export is provided; importing backups is not implemented.
- Existing sessions from the French version have their predefined statuses and risk categories migrated automatically. User-entered names, references and comments are preserved.
- Optional PDF / PNG / JPEG upload, maximum 10 MB. Only the fingerprint is retained; no OCR, automatic extraction or document archive.
- Duplicate detection is limited to the current session: SIREN plus normalized reference, or an identical SHA-256 file fingerprint. It cannot detect assignments on other platforms or every modified version of an invoice.
- SIREN validation checks the 9-digit format only, without checking company existence. Identity, documentation and financial information are simulated declarations.
- Metadata fingerprints are local SHA-256 records, without blockchain, certified timestamps or proof that a service was delivered.
- Transparent score out of 100: financial strength 40/25/5; payment history 25/15/0; buyer confirmation 25; documents 10. Financing requires a score ≥ 65, identity and documents declared complete, buyer confirmation and a future due date. The score is not a probability of default.
- Fee = face value × fee rate. Advance = face value − fee. No annualized interest or guaranteed return is quoted.
- Insolvency indemnity = min(advance, face value × hypothetical coverage). Residual capital = advance − indemnity. For a €10,000 invoice, 4% fee and 80% coverage: €9,600 advanced, €8,000 hypothetical indemnity and €1,600 residual capital at risk. This differs from the €2,000 of uncovered face value.
- Recourse is modeled as a potential claim against the SME for the residual capital after indemnification. Recovery is uncertain and does not eliminate lender exposure. No insurance coverage is assumed for disputes or fraud.
- Simplified assumptions exclude deductibles, waiting periods, contractual limits, recoveries, financing costs and insurance premiums. Non-recourse is not presented as universal protection.
- Use fictional documents only. This is an academic prototype, with no real financial service or legal validation.

## Deploy to Streamlit Community Cloud

Select the GitHub repository, the `main` branch and `app.py` as the main file. No secrets are required. Each browser session keeps its own data.

## Tests

```bash
python -m unittest -v
```

`test_engine.py` covers calculations, duplicates, eligibility, disputes, the financing/payment lifecycle and migration of existing French sessions. `test_ui.py` covers the screens and investor workflow using the Streamlit test runner.

## Files

- `app.py`: Streamlit interface and workflows.
- `engine.py`: business rules, calculations, sample data and session migration.
- `requirements.txt`: dependencies.
- `.streamlit/config.toml`: theme and upload limit.
- `test_engine.py`, `test_ui.py`: automated tests.
- `VERIFICATION.md`: validation performed and limitations.
