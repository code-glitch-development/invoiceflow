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

Open the address shown in the terminal, usually http://localhost:8501. The app opens without credentials. Buyer confirmation supports personal links, manual mail drafts and optional automatic email through Brevo.

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

- **SME:** upload, invoice checks, buyer confirmation links and tracking; submitted volume, incomplete files and simulated advances.
- **Investor:** financing, simulator and portfolio; eligible invoices, their volume and outstanding advances.

Each overview has its own headline, primary action and invoice queue. Guided next-step buttons still switch to the appropriate role and invoice automatically. Changing language preserves the selected role, page and saved data. These are presentation workspaces over the shared demo dataset, not access controls.

1. Open **SME → Overview**. New workspaces start empty; upload or enter your own invoice to begin.
2. Select **SME → Upload an invoice**. Enter a new invoice reference, a fictional 9-digit SIREN, an amount and a future due date. New invoices have pending identity/document review; suppliers cannot approve their own checks.
3. Select **SME → Buyer confirmation**. Enter a recipient email and prepare the mail. Send it from your own mail composer, open its link in another browser window, enter a name and confirm the invoice. Return to the SME page and refresh the response.
4. Select **Investor → Financing**. Choose the confirmed invoice, adjust the fee, recourse and hypothetical coverage, then simulate financing.
5. Open **Portfolio** to export CSV or JSON, and simulate late payment, a dispute, insolvency or full payment.
6. Use **Simulator** independently to explore advances, losses and hypothetical monthly and annual fee revenue.

The **Invoice progress** view shows Submitted → Confirmed → Eligible → Financed → Paid. Its next-step button opens the right role, page and invoice automatically. Select any invoice in Overview or Portfolio to resume its journey.

The **Invoice checks** page is read-only for the SME and shows identity/document review status. The supplier self-verification checkboxes and save-checks action have been removed from upload and review pages. New invoice identity/document flags start false, even after OCR or buyer confirmation. Existing historical demo declarations are preserved and explicitly labelled as declarations, not independent verification. The prototype currently has no independent review integration or reviewer workspace: new invoices remain blocked from financing until a separate reviewer process is implemented. Buyer confirmation can still be requested before that review is complete. Financing screens show each blocking reason and a complete checklist, using the same rules as the financing engine. Disputes, missing operational checks and expired due dates remain financing blockers. The former arbitrary score threshold has been removed.

The sidebar can clear the shared workspace only after an explicit deletion checkbox is selected. It never reloads sample invoices.

## Buyer confirmation by personal link

Use **SME → Buyer confirmation**. Enter the buyer email and the public address of
this InvoiceFlow app (normally prefilled from the browser), then click **Prepare
confirmation email**. **Open my email app** uses `mailto:` to open your configured
mail composer; you must send the message yourself. If no composer opens, expand
**Copy the link or email text** and paste it into Gmail, Outlook or another
webmail. This manual option requires no API account, key, SMTP configuration, extra
package or payment. Preparing a link does not send a message or prove delivery.

The recipient opens the deployed app using a personal random link. Their page
shows only the referenced invoice details, a name field, Confirm/Dispute, an
attestation checkbox and a comment. Opening a link (including an email preview)
never approves the invoice. Confirmation requires an explicit response and the
attestation; a dispute needs a reason and blocks financing. The name is declared,
not verified. The original uploaded document is not displayed because only its
fingerprint is archived. The buyer needs no InvoiceFlow account or installation.
The supplier uses **Refresh buyer response** to see the recorded decision.

Links carry a cryptographically random 256-bit bearer token. Only its SHA-256
hash is stored in the invoice JSON; plaintext tokens are held in the issuer's
current server session and email draft, not exported as invoice data. A link
expires after seven days, permits one response, and is bound to the invoice
business fields and original-file fingerprint. Any changed invoice, replaced
link, deleted record, or unsupported token is rejected. Expiry is checked at
submission. The response and UTC time are saved atomically, with name, declared
recipient address, decision, attestation and comment. Repeat submissions cannot
change a decision. Concurrent stale invoice edits are rejected by existing
version checks. Link preparation also rechecks the latest invoice in a database
transaction. To prepare a fresh email after losing the issuing browser session,
explicitly replace the old link; it immediately stops working. Existing completed
responses are preserved and cannot be overwritten through this UI.

The recipient route is handled before workspace navigation, portfolios and
exports. It never exposes other invoices in that page. The wider academic demo
still has freely interchangeable roles and shared workspace records: this is
not production authorisation or tenant isolation. Anyone with the link can
respond; the link does not independently prove civil identity, mailbox ownership
or authority to represent the buyer. A sender with access to the shared demo can
also copy/open the link. Call this **confirmation by personal link**, not
certified electronic signature, electronic-invoicing integration or a payment
guarantee. For a real financing service, authentication, authorisation, legally
adapted contracts and durable storage still need to be implemented.

The browser must be configured to open `mailto:` links for the composer button
to work; copying the prepared message into webmail is always available. The
public app URL must be reachable by the recipient. Localhost is accepted for
local testing but cannot be opened on another device. An optional
`INVOICEFLOW_PUBLIC_URL` environment variable can prefill a deployed URL; no
secrets are required. Existing Streamlit Yousign secrets can be removed; they
are no longer read. Legacy signature metadata is preserved but no provider
API is called. No database migration is needed. Reset or loss of the SQLite
file invalidates its links; preparing a new one cannot recover a deleted record.

## Automatic email through Brevo (optional Free plan)

The **Send confirmation email** button sends the link from the application via
Brevo's HTTPS API; no software installation, SMTP ports or extra Python package
is needed. **Prepare confirmation email** still only creates a manual draft.
The buyer confirmation remains the same personal-link workflow, with no certified
signature or independent identity verification.

Brevo currently advertises a Free plan including up to 300 transactional emails
per day without a credit card. Choose that plan and stay within its quota; this
app does not sign up for or upgrade any subscription. Availability, account
activation, sender/domain verification and delivery restrictions are controlled
by Brevo. Check current terms in your account. Sender verification and any domain
authentication requested by the provider must be completed before sending.

Create a free account, register and verify your sender, enable transactional
sending if needed, and create an API key (not an SMTP password). In Streamlit
Cloud → Settings → Secrets, add:

```toml
BREVO_API_KEY = "your-private-brevo-api-key"
BREVO_SENDER_EMAIL = "your-verified-sender@example.com"
```

Optional: `BREVO_SENDER_NAME="InvoiceFlow"`. The sender is fixed in server
configuration, not taken from public form inputs. No sending access code is
required. A legacy `MAIL_SEND_CODE` secret is ignored and can be removed. Sending
is available to visitors of this shared demo once Brevo is configured.
Never put API keys in GitHub, recipient links, form fields or chat. Without the
configuration, automatic send is disabled and the app explicitly says no mail
will be sent. The manual copy/composer path remains available.

Configure a reachable public app address, enter the recipient and click
**Send confirmation email**. A successful API response stores
its message identifier and displays **accepted for sending**. This is not proof
of delivery, mailbox ownership or buyer approval. Check the recipient's spam
folder and Brevo Transactional logs for delivery/bounce details. This version
has no delivery-event webhook or live inbox-status tracking. Only the buyer's
separate response confirms/disputes the invoice.

Each attempt is reserved in the invoice JSON before the network call. Refreshing
or double-clicking cannot send the same invitation twice. A definitive rejection
allows an explicit retry after correction. A timeout, ambiguous HTTP error or
malformed response is recorded as uncertain; resend and link replacement are
blocked until an operator checks the provider logs. There is no automatic retry.
An unfinished attempt left by a server crash also stays blocked. Inspect its
attempt tag in Brevo logs and back up the database before any manual recovery.
The response merge preserves a buyer decision received during the send. Accepted
emails may be sent again only by explicitly replacing the link (which invalidates
the old email's link) and submitting a new invitation.

No real email was sent in automated tests: network responses are mocked. Account
activation and a live delivery test must be completed by the account owner.

[Free plan and API](https://www.brevo.com/fr/products/transactional-email/),
[send API](https://developers.brevo.com/docs/send-a-transactional-email),
[sender setup](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email).

## Model and limitations

- Roles are freely interchangeable for presentation purposes: there is no authentication or access control.
- Invoice records are automatically stored in SQLite, shared across all visitors on one server. Closing a browser or opening another session does not delete them while the database file remains available. There is no authentication: use fictional data only. JSON export is provided; importing backups is not implemented.
- Existing sessions from the French version have their predefined statuses and risk categories migrated automatically. User-entered names, references and comments are preserved.
- Optional PDF / PNG / JPEG upload, maximum 10 MB. Uploading before filling the SME form proposes labelled supplier/buyer names, supplier SIREN (or the first nine digits of a labelled SIRET), invoice reference, total including tax, issue date and due date. Values remain editable and the user must review them before submitting. Extraction never marks identity, documents, buyer confirmation or risk declarations as verified.
- Text PDFs are read directly. Image-only pages and PNG/JPEG invoices use local Tesseract recognition in French/English. No external extraction API is called and files are not archived. Only the original file fingerprint and the submitted business fields are retained. Parsed fields live in the current browser session until submitted.
- This is best-effort extraction of labelled values, not a general document-understanding service. Unlabelled/ambiguous fields remain empty, conflicting values require manual entry, and totals in a detected non-EUR currency are not filled automatically. Amounts prefer total including tax over a remaining balance after a deposit. Numeric dates use DD/MM/YYYY or YYYY-MM-DD; other formats may need manual entry. Only the first three PDF pages are analysed; images are limited to 16 million pixels and each OCR operation to 15 seconds. Scans, unusual layouts and recognition errors may require corrections.
- Changing the file replaces previously populated invoice fields; identity and document verification are never inferred from extraction. A file that cannot be read leaves manual entry available. Re-running the same uploaded file (for example after a language switch) does not overwrite the user's corrections. Removing the file preserves the current draft.
- Duplicate detection covers the saved workspace: SIREN plus normalized reference, or an identical SHA-256 file fingerprint. It cannot detect assignments on other platforms or every modified version of an invoice.
- SIREN validation checks the 9-digit format only, without checking company existence. New identity/document checks remain pending; financial information is still declared. Legacy identity/document declarations are historical simulation values, not proof of verification.
- Metadata fingerprints are local SHA-256 records, without blockchain, certified timestamps or proof that a service was delivered.
- The old 0–100 declaration score, its 65/100 threshold and the financial-strength/payment-history dropdowns have been removed. Accounting risk is evaluated from buyer statements as documented below; checkbox flags never add financial-risk points.
- Fee = face value × fee rate. Advance = face value − fee. This remains a one-off fee; a separate annual rate powers the investor future-value simulation below. Neither value is a guaranteed return.
- Insolvency indemnity = min(advance, face value × hypothetical coverage). Residual capital = advance − indemnity. For a €10,000 invoice, 4% fee and 80% coverage: €9,600 advanced, €8,000 hypothetical indemnity and €1,600 residual capital at risk. This differs from the €2,000 of uncovered face value.
- Recourse is modeled as a potential claim against the SME for the residual capital after indemnification. Recovery is uncertain and does not eliminate lender exposure. No insurance coverage is assumed for disputes or fraud.
- Simplified assumptions exclude deductibles, waiting periods, contractual limits, recoveries, financing costs and insurance premiums. Non-recourse is not presented as universal protection.
- Use fictional documents only. This is an academic prototype, with no real financial service or legal validation.

## Deploy to Streamlit Community Cloud

Select the GitHub repository, the `main` branch and `app.py` as the main file. No secrets are required for the local SQLite default. Manual mail drafts require no secrets. Automatic mail requires the Brevo configuration below. All visitors share the same saved demo dataset.

`packages.txt` installs Tesseract and French/English language data on Community Cloud. For local OCR on Debian/Ubuntu, install `tesseract-ocr`, `tesseract-ocr-fra` and `tesseract-ocr-eng` with the system package manager; on macOS use `brew install tesseract tesseract-lang`. On Windows install Tesseract with the required languages and add its executable to PATH. Without the OCR executable, selectable-text PDFs still work and image uploads can be entered manually.

**Persistence limit:** Streamlit Community Cloud does not guarantee persistence of local files. A restart, redeployment or host cleanup may remove the SQLite file. This implementation therefore preserves data across browser sessions while the file exists, but does not promise durable storage on Community Cloud. For durable hosting, run the app with a persistent disk and set `INVOICEFLOW_DB_PATH` to a path on that disk, or add an external database backend before relying on long-term Cloud storage. See the [official persistence note](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

## Database operations

Default location: `data/invoiceflow.db`, relative to `app.py`. It is created automatically on first launch. Set the `INVOICEFLOW_DB_PATH` environment variable to use another location. SQLite is included with Python; no extra dependency is required.

An uninitialized database starts empty. Existing records are loaded on every rerun. A legacy in-memory session is imported on first initialization when available. A one-time transactional cleanup removes known built-in demo records without an uploaded file, matching their original supplier, buyer and invoice key. User invoices and uploaded-document records are preserved. No sample-population call runs during startup.

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

## Automatic accounts prefill and user-approved tariff

**Buyer accounts** now reads an uploaded PDF before creating the editable widgets.
Recognised company/SIREN, annual dates and accounting figures are prefilled with
page/line evidence. The provisional Z-double-prime and tariff update on reruns;
review and save the figures before they are used as the stored assessment.
Uploading a replacement clears previously proposed values; rerunning the same
file preserves manual corrections. The review checkbox confirms transcription
review only, not company identity, document authenticity or financing approval.

Extraction is local and conservative, with existing PDF/Tesseract dependencies
and no external AI/API fee. It analyses the first 16 pages, OCR at most six scanned
pages, and limits each OCR call to 15 seconds. It supports explicit French/English
accounting labels, signed/zero amounts, labelled current/prior-year columns and
page units (EUR, thousands/millions). Explicit gross/depreciation/net layouts are
handled when their ordering is clear. Conflicts and ambiguous columns stay empty.
EBITDA, net income and a bare retained-profit component are never silently treated
as EBIT or accumulated retained earnings. Total non-equity liabilities may be
derived as assets minus equity. Many tax-package/custom layouts will require
manual completion; this is not universal accounting-document understanding.

A calendar check infers the closing month/day from the submitted accounts. It
shows the latest completed period and uses a six-month V1 preparation window
before requiring the newer period, alongside the existing 548-day maximum age.
That window is an application assumption, not a legal deadline. For example, on
23 November 2026, a 31 December closing normally points to 2025 accounts, not
unclosed 2026 accounts. Previous-year accounts are not automatically fraudulent.
Future/obsolete dates, inconsistent accounts or an entered date/SIREN/company
contradicting detected PDF labels produce errors or require manual review.
No external filing register is queried: these checks cannot establish the latest
available filing or detect fraud by themselves. Unsupported OCR dates must be
reviewed manually. Recorded extraction evidence and review status are retained.

The default **Z-linked tariff (demo)** is the user-chosen commercial policy:

| Accounting state | Base | Additional premium | Annual continuous tariff | Automatic tariff simulation |
| --- | ---: | ---: | ---: | --- |
| Z > 2.60 | 5% | 0 points | 5% | Subject to operational eligibility |
| 1.10 <= Z <= 2.60 | 5% | 2 points | 7% | Subject to operational eligibility |
| Z < 1.10 | 5% | 4 points | 9% indicative | Manual review; blocked |
| No buyer accounts supplied | 5% | 5 points | 10% | Subject to operational eligibility; risk remains unassessed |
| Accounts supplied but unusable | — | — | 10% indicative fallback | Correct the accounts or request manual review; blocked |

These premiums are explicit commercial choices, not calibrated default
probabilities, market quotations or evidence that a rate compensates losses.
The 10% tier is an information-uncertainty surcharge selected by the user, not a
claim that unknown risk is measurable. The previous no-quote-without-accounts
policy has been replaced only in this tariff mode. The optional expected-cashflow
sandbox still requires an accounting assessment and explicit fictional-scenario
opt-in; its PD and costs are not added on top of the tariff.

For a known invoice face FV, tariff pricing uses
`PV = FV * exp(-(annual_rate_percent/100) * actual_days/365)`.
The advance is rounded down to cents, gross spread is `FV - PV`, and operation
return is spread/PV. The stored cash-flow annual equivalent accounts for rounding,
so saved future value at maturity reconciles with the face amount. Costs, fees,
insurance and losses are not secretly deducted or covered by this simple tariff.
The dashboard therefore remains gross and conditional on full payment.

Tariff and legacy cash-flow quotes are selectable in the investor opportunity
screen. Missing PD/LGD for tariff quotes are shown as unavailable, never zero.
The invoice dossier rechecks and saves its tariff, accounting zone, source and
quote fingerprint. Batch financing re-evaluates the current model/record version
atomically; changed risk data or expiry cannot silently reuse an old quote.
Existing financed operations keep their original amounts and assumptions.

## Buyer accounting indicator: Altman Z-double-prime

Open **SME or Investor → Buyer accounts**, select the invoice, attach the buyer's
balance sheet and income statement in a single PDF (maximum 5 MB), and review the seven required accounting values proposed by local extraction. Unrecognised values start empty. Identify
the buyer by the name on the invoice and SIREN (format only), a complete annual
period and source/page references. The source PDF is archived as a SQLite BLOB,
linked by SHA-256; the invoice JSON export contains its provenance and figures,
not the PDF bytes. The separate PDF download is available on the accounting page.
A database reset clears both invoices and these archived financial documents.

The implemented non-manufacturing variant is:

`Z'' = 6.56 × (current assets − current liabilities)/assets`
`    + 3.26 × retained earnings/assets + 6.72 × EBIT/assets`
`    + 1.05 × book equity/total liabilities`.

It has no emerging-market +3.25 intercept and is not scaled to 100. Historical
zones are below 1.10 (distress), 1.10 through 2.60 inclusive (grey), and above 2.60
(lower distress in this model, never a payment guarantee). Floating-point noise
is stabilised at 12 decimal places before threshold comparison. The interface
also exposes current ratio, equity/assets, EBIT/assets, each model ratio and its
weighted contribution. These figures assess the buyer, not the invoice supplier.

Sources: Horváthová and Mokrišová (2018), *Risk of Bankruptcy, Its Determinants
and Models*, section 3.4, https://doi.org/10.3390/risks6040117 ; Chris Ireland's
NYU research report (2005), appendix A, within
https://archive.nyu.edu/jspui/bitstream/2451/26400/2/FIN-05-001.pdf . These sources
are linked in the app. No accuracy claim for current French SMEs is made.

The V1 restricts this indicative model to non-financial, non-manufacturing
companies with complete annual accounts. Missing accounts/values, incompatible
scope, an invalid period, wrong named buyer, unreadable PDF, zero/non-positive
model denominators or inconsistent balance sheet produce **Risk not assessed**,
not a zero score or a favourable default. Negative equity, EBIT and retained
losses are permitted. Balance-sheet identity has a EUR 1 rounding tolerance.
The freshness ceiling of 548 days is an explicit V1 data policy, not a published
Altman coefficient or a universal accounting rule. A previously valid assessment
becomes unassessed for current use when it ages beyond that ceiling.

Retained earnings must be reconciled as accumulated retained profits/losses,
excluding contributed capital/share premium; EBIT must be reconciled before
interest and tax, not copied from EBITDA or net profit. Ask the accountant if
mapping a French statement is ambiguous. All amounts use EUR, not thousands.
The code validates arithmetic and provenance fields, not document authenticity,
company identity, source accuracy or sector suitability beyond the declaration.
Local accounting OCR/prefill is available as described above; no official rating API or independent credit analyst is claimed.
Use public or anonymised statements in the shared academic workspace.

A financial indicator neither approves identity/documents nor calibrates PD,
LGD or funding costs. The default commercial tariff now quotes 10% for missing accounts while keeping risk unassessed. The older scenario-pricing sandbox is available only after the user explicitly enables fictional pricing and supplies usable accounts. Its colour
badges describe pricing scenarios, distinct from the document-based accounting
zone. A documented, validated pricing/credit model is still required for a real
financing offer. Operational eligibility checks remain separate. Existing
financings keep their amounts and saved assumptions; new financings with an
accounting indicator snapshot its inputs/result for audit without changing rates.
No sample accounts are generated or loaded into production data. Synthetic
statement inputs exist only in tests, clearly marked as fixtures.

## Risk-sensitive pricing

Open **Investor → Financing**. In the optional expected-cashflow mode, no yield is proposed without usable buyer accounts. Even after an accounting assessment, this mode requires explicit simulation opt-in. The optional **internal fictional annual cohort** uses four defaults among 200 simulated buyers give an observed annual rate of 2%. Other explicitly selected fictional groups give different observed rates. Counts are invented aggregates for a completed calendar year, separate from the invoices currently moving through the workflow. They do not constitute empirical evidence about an actual buyer, and the accounting score is never converted to a cohort or PD.

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

Workspaces no longer receive generated invoices. Existing built-in examples are
removed once on startup; unrelated user records and uploaded documents remain.
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

### Portfolio return dashboard

Portfolio highlights outstanding capital, projected gross return across all paid
and unpaid financed operations, and the capital-weighted annual continuous rate
of unpaid financings. Supporting metrics and formulas are under Portfolio
performance details. Overdue counts and capital remain visible as an alert.

- Projected return = (realized gross gains + full-payment potential gross gains)
  / cumulative capital advanced on those financed operations. This is not an
  annualised account return and does not assume reinvestment.
- Realized return uses only the gross gain and original advances of paid invoices.
- The annual indicator averages the original continuous cash-flow rates of unpaid
  invoices, weighted by their advances. Each rate uses the saved financing date
  and expected collection date, or invoice due date for manual financings. It
  does not use the independent annual-interest sandbox setting and does not
  increase merely because today's date moves forward. It is not portfolio XIRR.
- If any unpaid financing lacks valid dates, the annual average is unavailable,
  with a count of incomplete records; it never silently reports a partial average.
  Empty returns display a dash; a valid zero-gain investment displays 0%.

All figures are gross and simulated. Potential returns assume full collection,
including for incident invoices; they exclude unrecorded recoveries, hypothetical
insurance and exponential theoretical interest. They do not establish net
profitability or calibrated risk-adjusted performance.

### Cleanup of the accidental ten-supplier batch

A separate one-time cleanup removes records tagged with
`demo_source=requested-ten-suppliers-v1` that have no uploaded file. This handles
databases that already loaded that batch before automatic insertion was reverted.
The cleanup runs before the workspace is displayed and applies to the shared
records in every role, not just the SME table. Uploaded documents and manually
created records without that provenance are preserved. No examples are recreated.


## InvoiceFlow platform commission

New financing simulations charge the SME a one-off platform commission of **1% of
invoice face value including tax**, in addition to the financing discount. For a
EUR 10,000 invoice due in 60 days at the 5% annual continuous tariff, investor
capital is EUR 9,918.14, investor gross gain is EUR 81.86, InvoiceFlow commission
is EUR 100, SME net proceeds are EUR 9,818.14 and total SME cost is EUR 181.86.
The investor still receives the invoice face amount if paid in full. The platform
commission is not annualized, added to investor returns or charged at repayment.

The financing dossier, comparison, offer details, selection confirmation and
saved portfolio show the commission separately. The SME overview totals net
proceeds, while investor budgets, exposure and returns use the full investor
capital. The independent revenue simulator now uses only the 1% platform fee,
not the investor discount, for hypothetical platform revenue. Other charges and
any VAT on the platform commission are not modelled.

Pricing reports include the fee, SME net proceeds and total SME cost in their
audit snapshot. Saving recomputes the amounts server-side. A nonpositive net
payment blocks financing. No migration is required: existing financed records
keep their original terms and are never assigned a commission retroactively.
