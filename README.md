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

1. Open **SME → Overview**. The requested batch provides ten clearly labelled fictional suppliers; you can also upload or enter your own invoice.
2. Select **SME → Upload an invoice**. Enter a new invoice reference, a fictional 9-digit SIREN, an amount and a future due date. Select **Strong** and **On time**, and tick both simulated checks.
3. Select **Buyer → Buyer confirmation**. Choose the buyer and invoice, check the confirmation box and save. You can also dispute an invoice with a reason.
4. Select **Investor → Financing**. Choose the confirmed invoice, adjust the fee, recourse and hypothetical coverage, then simulate financing.
5. Open **Portfolio** to export CSV or JSON, and simulate late payment, a dispute, insolvency or full payment.
6. Use **Simulator** independently to explore advances, losses and hypothetical monthly and annual fee revenue.

The **Invoice progress** view shows Submitted → Confirmed → Eligible → Financed → Paid. Its next-step button opens the right role, page and invoice automatically. Select any invoice in Overview or Portfolio to resume its journey.

The **Invoice checks** page lets the SME complete simulated identity/document checks without changing confirmed invoice terms. Financing screens show each blocking reason and a complete checklist, using the same rules as the financing engine. Low scores, disputes and expired due dates are never bypassed.

The sidebar can clear the shared workspace only after an explicit deletion checkbox is selected. It never reloads sample invoices.

## Model and limitations

- Roles are freely interchangeable for presentation purposes: there is no authentication or access control.
- Invoice records are automatically stored in SQLite, shared across all visitors on one server. Closing a browser or opening another session does not delete them while the database file remains available. There is no authentication: use fictional data only. JSON export is provided; importing backups is not implemented.
- Existing sessions from the French version have their predefined statuses and risk categories migrated automatically. User-entered names, references and comments are preserved.
- Optional PDF / PNG / JPEG upload, maximum 10 MB. Uploading before filling the SME form proposes labelled supplier/buyer names, supplier SIREN (or the first nine digits of a labelled SIRET), invoice reference, total including tax, issue date and due date. Values remain editable and the user must review them before submitting. Extraction never marks identity, documents, buyer confirmation or risk declarations as verified.
- Text PDFs are read directly. Image-only pages and PNG/JPEG invoices use local Tesseract recognition in French/English. No external extraction API is called and files are not archived. Only the original file fingerprint and the submitted business fields are retained. Parsed fields live in the current browser session until submitted.
- This is best-effort extraction of labelled values, not a general document-understanding service. Unlabelled/ambiguous fields remain empty, conflicting values require manual entry, and totals in a detected non-EUR currency are not filled automatically. Amounts prefer total including tax over a remaining balance after a deposit. Numeric dates use DD/MM/YYYY or YYYY-MM-DD; other formats may need manual entry. Only the first three PDF pages are analysed; images are limited to 16 million pixels and each OCR operation to 15 seconds. Scans, unusual layouts and recognition errors may require corrections.
- Changing the file replaces previously populated invoice fields and clears verification checkboxes. A file that cannot be read leaves manual entry available. Re-running the same uploaded file (for example after a language switch) does not overwrite the user's corrections. Removing the file preserves the current draft.
- Duplicate detection covers the saved workspace: SIREN plus normalized reference, or an identical SHA-256 file fingerprint. It cannot detect assignments on other platforms or every modified version of an invoice.
- SIREN validation checks the 9-digit format only, without checking company existence. Identity, documentation and financial information are simulated declarations.
- Metadata fingerprints are local SHA-256 records, without blockchain, certified timestamps or proof that a service was delivered.
- Transparent score out of 100: financial strength 40/25/5; payment history 25/15/0; buyer confirmation 25; documents 10. Financing requires a score ≥ 65, identity and documents declared complete, buyer confirmation and a future due date. The score is not a probability of default.
- Fee = face value × fee rate. Advance = face value − fee. This remains a one-off fee; a separate annual rate powers the investor future-value simulation below. Neither value is a guaranteed return.
- Insolvency indemnity = min(advance, face value × hypothetical coverage). Residual capital = advance − indemnity. For a €10,000 invoice, 4% fee and 80% coverage: €9,600 advanced, €8,000 hypothetical indemnity and €1,600 residual capital at risk. This differs from the €2,000 of uncovered face value.
- Recourse is modeled as a potential claim against the SME for the residual capital after indemnification. Recovery is uncertain and does not eliminate lender exposure. No insurance coverage is assumed for disputes or fraud.
- Simplified assumptions exclude deductibles, waiting periods, contractual limits, recoveries, financing costs and insurance premiums. Non-recourse is not presented as universal protection.
- Use fictional documents only. This is an academic prototype, with no real financial service or legal validation.

## Deploy to Streamlit Community Cloud

Select the GitHub repository, the `main` branch and `app.py` as the main file. No secrets are required for the local SQLite default. All visitors share the same saved demo dataset.

`packages.txt` installs Tesseract and French/English language data on Community Cloud. For local OCR on Debian/Ubuntu, install `tesseract-ocr`, `tesseract-ocr-fra` and `tesseract-ocr-eng` with the system package manager; on macOS use `brew install tesseract tesseract-lang`. On Windows install Tesseract with the required languages and add its executable to PATH. Without the OCR executable, selectable-text PDFs still work and image uploads can be entered manually.

**Persistence limit:** Streamlit Community Cloud does not guarantee persistence of local files. A restart, redeployment or host cleanup may remove the SQLite file. This implementation therefore preserves data across browser sessions while the file exists, but does not promise durable storage on Community Cloud. For durable hosting, run the app with a persistent disk and set `INVOICEFLOW_DB_PATH` to a path on that disk, or add an external database backend before relying on long-term Cloud storage. See the [official persistence note](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

## Database operations

Default location: `data/invoiceflow.db`, relative to `app.py`. It is created automatically on first launch. Set the `INVOICEFLOW_DB_PATH` environment variable to use another location. SQLite is included with Python; no extra dependency is required.

An uninitialized database receives the explicitly requested ten-supplier presentation batch once. Existing records are loaded on every rerun. A legacy in-memory session is imported on first initialization when available. A one-time transactional cleanup removes known built-in demo records without an uploaded file, matching their original supplier, buyer and invoice key. User invoices and uploaded-document records are preserved. Only the explicitly requested ten-supplier batch is applied once; the removed catalog is never restored.

Each change updates one invoice in a transaction. A version check rejects stale writes, and database uniqueness constraints reject repeated supplier references and identical file hashes across sessions. Failed saves do not show a success message or replace saved data. Reset is atomic.

Back up the SQLite file while the application is stopped. Database files, uploaded documents, secrets and local data are excluded from Git. The JSON export is also available for review; it is not an automatic restore mechanism.

## Investor future value

The investor screens use `FV = P × exp(t × r / 100)`: `P` is the original capital advanced to the SME, `r` is the annual continuous-interest rate expressed as a percentage (5 means 5%), and `t` is years without payment. Default Financing now derives the advance and rate jointly from documented risk/cost assumptions. The independent manual mode and Simulator retain a 5% illustrative starting value. Future value is never added a second time to fees, insurance indemnity or collected income.

- **Financing:** use risk-based pricing by default, or explicitly select the independent manual demonstration. Simulating funding saves the date, rate and advance, plus the complete risk-pricing snapshot when applicable.
- **Portfolio:** future value, theoretical interest and elapsed days are calculated automatically when the view is loaded or refreshed. Time starts on the financing date, including days before the invoice due date. Calendar days are divided by 365, including actual leap-year days (Actual/365 fixed). Today's date uses Europe/Paris. A projection-date toggle lets investors explore longer periods without payment.
- **Payment:** a simulated full payment records the payment date. Calculations stop on that date, even when a later projection date is selected. Late payment, insolvency or dispute does not itself simulate cash collection; any continuing exponential growth is only a theoretical scenario.
- **Existing records:** the app never invents missing financing/payment dates or retroactively changes saved amounts. The investor can explicitly configure missing dates and an annual assumption. A recorded financing date cannot be changed; the rate remains editable as a simulation assumption.
- **Simulator:** enter the time directly in years (fractional values are supported). Calculations always use the original advance and total elapsed time, so repeated reruns cannot compound the same period twice. Interest settings and payment dates survive database reopening and are included in JSON exports.

The mathematical convention is continuous compounding; see [OpenStax](https://openstax.org/books/college-algebra-corequisite-support/pages/6-1-exponential-functions). This model does not establish contractual interest, penalties, collectible debt or guaranteed payment.

## Risk-sensitive pricing

Open **Investor → Financing**. Default risk pricing now starts with an **internal fictional annual cohort**: four defaults among 200 simulated buyers give an observed annual rate of 2%. Other explicitly selected fictional groups give different observed rates. Counts are invented aggregates for a completed calendar year, separate from the invoices currently moving through the workflow. They do not constitute empirical evidence about an actual buyer, and the demo score or declared payment-history dropdown does not automatically assign a buyer to a cohort.

The screen shows numerator, denominator, annual period and data origin. PD and cohort provenance are read-only; costs and recovery assumptions remain adjustable. Cohort counts/version are checked on pricing and saved in the JSON report. Switching to manual PD inputs permits explicit alternative assumptions; missing inputs/source still block funding. No credit-data provider or external API is required for the default demonstration.

The model scales one-year PD to the actual tenor using constant survival intensity, prices the maximum advance from expected discounted performing/default cash flows, and derives the annual continuous equivalent. It accounts separately for expected collection delay, recovery lag, upfront costs and effective annual funding/capital/margin budgets. Missing/old data and the configured rate limit can block an offer. Existing workflow requirements remain binding.

The screen exposes the cash-flow breakdown, mechanical stress sensitivities and a downloadable JSON calculation report. Funding rechecks the quote and persists its assumptions; saved risk-based rates cannot be overwritten through the legacy interest editor. The full model derivation, assumptions, example and empirical calibration requirements are in [PRICING_MODEL.md](PRICING_MODEL.md). Mathematical tests do not establish that assumed PD/LGD predict real losses.

## Tests

```bash
python -m unittest -v
```

`test_engine.py` covers calculations, duplicates, eligibility explanations, file completion, progress history, disputes, the financing/payment lifecycle and migration of existing French sessions. `test_storage.py` covers reopening the database, saved financing, cross-session duplicates, stale writes, atomic reset and storage errors. `test_i18n.py` checks translation templates, localized exports and preservation of business values. `test_ui.py` covers both languages, all screens and language switching during the investor workflow using the Streamlit test runner.

## Files

- `assets/invoiceflow-logo.png`: InvoiceFlow logo, displayed on a white panel in the dark sidebar. The asset path is resolved relative to `app.py`.
- `app.py`: Streamlit interface and workflows.
- `invoice_extraction.py`: local PDF text extraction, OCR, labelled-field parsing and session prefill.
- `packages.txt`: OCR executable and language dependencies for Community Cloud.
- `workspaces.py`: role navigation, overview metrics and actionable invoice queues.
- `future_value.py`: continuous compounding, Actual/365 duration and payment-date stopping.
- `risk_pricing.py`, `pricing_ui.py`: documented expected-cash-flow pricing and investor controls.
- `demo_pd.py`: fictional completed-year borrower aggregates and observed default-rate calculation.
- `PRICING_MODEL.md`: derivation, conventions, limitations and calibration requirements.
- `i18n.py`: English/French presentation translations.
- `storage.py`: transactional SQLite persistence.
- `engine.py`: business rules, calculations, sample data and session migration.
- `requirements.txt`: dependencies.
- `.streamlit/config.toml`: theme and upload limit.
- `test_engine.py`, `test_i18n.py`, `test_storage.py`, `test_ui.py`: automated tests.
- `test_workspaces.py`: role-specific metrics, queues, navigation and translation coverage.
- `test_future_value.py`: percentage/year conversion, invalid inputs, no double compounding, legacy records and payment stopping. Storage and interface tests also cover saved interest settings and projections.
- `test_risk_pricing.py`: horizon PD, cash-flow consistency, policy blocks, sensitivities, saved snapshots and prevention of double charging.
- `test_demo_pd.py`: aggregate consistency, completed annual windows, fictional provenance and cohort validation.
- `test_extraction.py`: native/scanned PDFs, PNG/JPEG OCR, ambiguity, invalid files, currency/date handling and preservation of manual corrections.
- `VERIFICATION.md`: validation performed and limitations.


### Investor opportunity workspace

The Investor home shows eligible invoices as cards with model-priced advances,
expected payment dates, and gross gains conditional on full payment, before costs.
Filter by total budget, expected payment horizon (including the assumed delay),
and fictional borrower scenario. Select up to three whole invoices; filtered-out
selections remain in the comparator and count toward the total budget.

The comparator and selection summary show aggregate capital and exposure by
buyer name. `Simulation assumptions` sets a common scenario per buyer and shared
pricing costs. These scenarios use the existing fictional annual cohorts, not
calibrated client ratings. Adding transactions cannot dilute their annual PD.
The detailed financing and simulator screens remain accessible.

Opportunity cards and the comparator distinguish gross return over the operation
(`(face value - advance) / advance`) from its annual continuous equivalent.
Both assume full payment on the expected collection date, before costs and losses;
neither is a guaranteed or risk-adjusted net return.

The Investor Portfolio shows outstanding principal, simulated full-payment
receipts (including returned principal), realized gross gains after simulated
payment, potential gross gains on unpaid financed invoices, overdue principal,
and overdue invoice count. These totals cover the whole saved workspace and do
not follow opportunity or portfolio status filters. They exclude theoretical
exponential interest, hypothetical insurance and unrecorded recoveries.
Potential gains include incident invoices under a full-payment assumption.
Portfolio details group unpaid principal and its share by normalized buyer name
and list overdue invoices. A due date before today (Europe/Paris), or an explicit
late-payment event, marks an unpaid financed invoice overdue; due today does not.
This remains a shared fictional portfolio, not an authenticated personal account.

`Simulate this selection` opens a review. Confirmation rechecks invoice versions,
eligibility, current quotes, and the aggregate budget inside one database
transaction. Either the entire selection is recorded or none is. Changes to
quotes, budget, selection, or the shared portfolio invalidate the review. No
money is transferred. Existing financed invoices retain their saved pricing.

The old 30-invoice catalog is removed once on startup; unrelated user records
and uploaded documents remain. Only the separately requested ten-supplier batch
is added once.
The old catalog generators remain as automated-test fixtures and cleanup identity
references, and are not exposed as application actions.

### Simplified demonstration interface

The Opportunities screen focuses on capital to advance, payment horizon and
potential gross gain. Each card has a collapsed return/payment section and a
primary `Review this financing` action. Portfolio totals appear only in Portfolio.
An empty selection does not show a comparison or funding summary.

Financing keeps a visible quote and financing action, with pricing inputs,
financing options, risk/exposure details and calculation breakdown in collapsed
sections. All widgets remain rendered and their original validation and saved
assumptions still apply. Blockers remain visible outside the collapsed sections.

For a five-minute demo, use Opportunities → Review this financing → Simulate
financing → Portfolio. For a usability session, ask someone unfamiliar with the
app to complete that task without oral guidance; record completion, time, wrong
turns and any requests for help. Automated workflow checks are not a substitute
for that participant session.

### Understanding the displayed rates

Risk pricing is an illustrative model, not a market quote or a calibrated buyer
assessment. Default assumptions include 3% annual funding cost, 1% capital charge,
2% target margin, EUR 20 upfront costs, 60% nominal LGD, 5 days expected payment
delay and 90 days recovery lag. The Central fictional cohort has 2% annual PD.
The model first solves the advance from expected discounted payment/recovery
cash flows. It then derives three different ratios, which must not be confused:

- Fee on invoice: `(face - advance) / face`.
- Gross return over the operation: `(face - advance) / advance`.
- Annual continuous equivalent: `100 * ln(face / advance) * 365 / horizon_days`.

With a EUR 10,000 invoice due in 60 days, Central defaults use a 65-day collection
horizon and produce a EUR 9,855.03 advance: EUR 144.97 gross gain, 1.4497% fee on
face, 1.4710% return over the operation and 8.2002% annual continuous equivalent.
For EUR 1,000 due in 10 days (15-day horizon), the same assumptions produce
EUR 977.09 advanced and EUR 22.91 gross gain: 2.3447% over the operation but
56.3962% annual continuous equivalent. Fixed EUR 20 costs explain much of that
short-term annualisation. Neither annual rate is an observed buyer credit rate
or a guarantee of receipts. Quotes are recalculated as the remaining horizon
changes; confirmed transactions keep their saved terms.

The manual simulator separately sets a one-off fee and a theoretical annual
interest assumption. Those independent inputs do not establish consistent
contractual cash flows, and theoretical interest must never be added to the
invoice repayment or presented as collected income.

### Requested ten-supplier presentation batch

Following the removal of the old 30-record catalog, an explicitly requested batch
adds ten fictional invoices once per database. Each supplier is distinct and
labelled Démo. All ten invoices are EUR 10,000 due in 60 days, with the same
fictional Central risk assumptions, so their initial model quotes match. Buyer
confirmation and checks are simulated; none is already financed. The EUR 100,000
total face value is distinct from the sum of advances offered.

The batch preserves existing user invoices, never overwrites edits and is not
recreated after the workspace is cleared. The original catalog stays removed.
