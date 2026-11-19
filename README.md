# InvoiceFlow ↗

A bilingual English/French Streamlit demo for invoice financing and reverse factoring, based on the supplied InvoiceFlow concept. All companies and transactions are fictional. No money is transferred.

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

## Language / Langue

Use the **EN / FR** selector at the top of the sidebar to switch language instantly.
Menus, forms, messages, table headers and displayed statuses follow the selection.
Invoice records and financing values are preserved; internal identifiers remain in English.
CSV exports follow the selected language. JSON exports retain the canonical data for portability.
The choice is kept for the current browser session. Submitted data is retained when switching languages; submit an open form before switching to preserve any draft edits.

Utilisez le sélecteur **EN / FR** en haut de la barre latérale pour changer de langue.
Les factures et leurs financements sont conservés. Validez un formulaire ouvert avant de changer de langue pour conserver les modifications non envoyées.

## Three-minute demo

The demo role selector opens a distinct workspace and returns to its overview:

- **SME:** upload, invoice checks and tracking; submitted volume, incomplete files and simulated advances.
- **Buyer:** confirmation and tracking; pending decisions, their total amount and disputes.
- **Investor:** financing, simulator and portfolio; eligible invoices, their volume and outstanding advances.

Each overview has its own headline, primary action and invoice queue. Guided next-step buttons still switch to the appropriate role and invoice automatically. Changing language preserves the selected role, page and saved data. These are presentation workspaces over the shared demo dataset, not access controls.

1. Open the **SME → Overview** to explore the four fictional examples.
2. Select **SME → Upload an invoice**. Enter a new invoice reference, a fictional 9-digit SIREN, an amount and a future due date. Select **Strong** and **On time**, and tick both simulated checks.
3. Select **Buyer → Buyer confirmation**. Choose the buyer and invoice, check the confirmation box and save. You can also dispute an invoice with a reason.
4. Select **Investor → Financing**. Choose the confirmed invoice, adjust the fee, recourse and hypothetical coverage, then simulate financing.
5. Open **Portfolio** to export CSV or JSON, and simulate late payment, a dispute, insolvency or full payment.
6. Use **Simulator** independently to explore advances, losses and hypothetical monthly and annual fee revenue.

The **Invoice progress** view shows Submitted → Confirmed → Eligible → Financed → Paid. Its next-step button opens the right role, page and invoice automatically. Select any invoice in Overview or Portfolio to resume its journey.

The **Invoice checks** page lets the SME complete simulated identity/document checks without changing confirmed invoice terms. Financing screens show each blocking reason and a complete checklist, using the same rules as the financing engine. Low scores, disputes and expired due dates are never bypassed.

Use the sidebar to reset the shared demo. Resetting replaces the data for every visitor. Example due dates are relative to the date the database is first initialized or reset.

## Model and limitations

- Roles are freely interchangeable for presentation purposes: there is no authentication or access control.
- Invoice records are automatically stored in SQLite, shared across all visitors on one server. Closing a browser or opening another session does not delete them while the database file remains available. There is no authentication: use fictional data only. JSON export is provided; importing backups is not implemented.
- Existing sessions from the French version have their predefined statuses and risk categories migrated automatically. User-entered names, references and comments are preserved.
- Optional PDF / PNG / JPEG upload, maximum 10 MB. Only the fingerprint is retained; no OCR, automatic extraction or document archive.
- Duplicate detection covers the saved workspace: SIREN plus normalized reference, or an identical SHA-256 file fingerprint. It cannot detect assignments on other platforms or every modified version of an invoice.
- SIREN validation checks the 9-digit format only, without checking company existence. Identity, documentation and financial information are simulated declarations.
- Metadata fingerprints are local SHA-256 records, without blockchain, certified timestamps or proof that a service was delivered.
- Transparent score out of 100: financial strength 40/25/5; payment history 25/15/0; buyer confirmation 25; documents 10. Financing requires a score ≥ 65, identity and documents declared complete, buyer confirmation and a future due date. The score is not a probability of default.
- Fee = face value × fee rate. Advance = face value − fee. No annualized interest or guaranteed return is quoted.
- Insolvency indemnity = min(advance, face value × hypothetical coverage). Residual capital = advance − indemnity. For a €10,000 invoice, 4% fee and 80% coverage: €9,600 advanced, €8,000 hypothetical indemnity and €1,600 residual capital at risk. This differs from the €2,000 of uncovered face value.
- Recourse is modeled as a potential claim against the SME for the residual capital after indemnification. Recovery is uncertain and does not eliminate lender exposure. No insurance coverage is assumed for disputes or fraud.
- Simplified assumptions exclude deductibles, waiting periods, contractual limits, recoveries, financing costs and insurance premiums. Non-recourse is not presented as universal protection.
- Use fictional documents only. This is an academic prototype, with no real financial service or legal validation.

## Deploy to Streamlit Community Cloud

Select the GitHub repository, the `main` branch and `app.py` as the main file. No secrets are required for the local SQLite default. All visitors share the same saved demo dataset.

**Persistence limit:** Streamlit Community Cloud does not guarantee persistence of local files. A restart, redeployment or host cleanup may remove the SQLite file. This implementation therefore preserves data across browser sessions while the file exists, but does not promise durable storage on Community Cloud. For durable hosting, run the app with a persistent disk and set `INVOICEFLOW_DB_PATH` to a path on that disk, or add an external database backend before relying on long-term Cloud storage. See the [official persistence note](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

## Database operations

Default location: `data/invoiceflow.db`, relative to `app.py`. It is created automatically on first launch. Set the `INVOICEFLOW_DB_PATH` environment variable to use another location. SQLite is included with Python; no extra dependency is required.

Only an uninitialized database receives the example dataset. Existing records are loaded on every rerun. A legacy in-memory session is imported on first initialization when available. Saved samples keep their original due dates; use Reset demo for fresh examples.

Each change updates one invoice in a transaction. A version check rejects stale writes, and database uniqueness constraints reject repeated supplier references and identical file hashes across sessions. Failed saves do not show a success message or replace saved data. Reset is atomic.

Back up the SQLite file while the application is stopped. Database files, uploaded documents, secrets and local data are excluded from Git. The JSON export is also available for review; it is not an automatic restore mechanism.

## Tests

```bash
python -m unittest -v
```

`test_engine.py` covers calculations, duplicates, eligibility explanations, file completion, progress history, disputes, the financing/payment lifecycle and migration of existing French sessions. `test_storage.py` covers reopening the database, saved financing, cross-session duplicates, stale writes, atomic reset and storage errors. `test_i18n.py` checks translation templates, localized exports and preservation of business values. `test_ui.py` covers both languages, all screens and language switching during the investor workflow using the Streamlit test runner.

## Files

- `app.py`: Streamlit interface and workflows.
- `workspaces.py`: role navigation, overview metrics and actionable invoice queues.
- `i18n.py`: English/French presentation translations.
- `storage.py`: transactional SQLite persistence.
- `engine.py`: business rules, calculations, sample data and session migration.
- `requirements.txt`: dependencies.
- `.streamlit/config.toml`: theme and upload limit.
- `test_engine.py`, `test_i18n.py`, `test_storage.py`, `test_ui.py`: automated tests.
- `test_workspaces.py`: role-specific metrics, queues, navigation and translation coverage.
- `VERIFICATION.md`: validation performed and limitations.

