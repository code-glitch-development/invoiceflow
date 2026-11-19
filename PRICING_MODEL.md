# Expected-cash-flow invoice pricing, version 1

This is an auditable research prototype. It supplies a consistent price **conditional on documented assumptions**, not a validated rating system, a market fair-value estimate or a banking/regulatory capital model. No customer default history or independent risk-data feed has been supplied to calibrate PD, recoveries or payment timing.

## Inputs and provenance

For each buyer/invoice, enter:

- A **one-year real-world probability of default**, in percent, from a dated and identified source. It is never inferred from the demo score, `Strong`/`Weak`, or the declared payment-history dropdown.
- **Nominal LGD**: the fraction of advanced principal not recovered in default, net of recovery costs but **before time discounting**. Recoveries below are discounted separately. An economic LGD already incorporating discounted recovery cash flows cannot be used unchanged without reconciliation.
- Expected additional collection delay after the due date, and an additional default-recovery lag after that collection date. Both are whole calendar days.
- Annual effective-rate budgets for funding costs, capital allocation and target margin. The capital charge is a supplied cost budget, not a calculation of regulatory or economic capital.
- Upfront transaction costs in euros, paid at origination. Do not include the same costs in both LGD net recovery costs and upfront costs.
- Source reference, observation date, data origin (`Illustrative assumptions` or `User-provided, unverified`), optional notes, maximum data age and an investor annual-rate ceiling.

All credit/cost inputs start empty. An explicit button can load a fictional example: annual PD 2%, nominal LGD 60%, funding/capital/margin budgets 3%/1%/2%, EUR 20 upfront costs, five days additional payment delay and 90 days additional recovery lag. These are test assumptions, not empirical estimates or suggested market pricing.

The existing coverage slider and recourse toggle do not lower PD or LGD automatically. Credible recovery assumptions would require analysing actual enforceable protection, exclusions, counterparty strength, timing and recovery costs. The current application does not verify that evidence.

## Time, default probability and discounting

Let:

- `F` be the invoice face amount, and `P` the amount advanced to the SME.
- `T = (days until due date + expected collection delay) / 365`.
- `L = additional recovery lag / 365`.
- `p1` be the one-year PD as a decimal.
- `R = 1 - nominal LGD` be net nominal recovery as a fraction of `P`.
- `C` be upfront costs in euros.
- `a` be the sum of annual effective funding/capital/margin budgets as decimals.

The constant-default-intensity assumption gives:

```text
lambda = -ln(1 - p1)
p(T) = 1 - exp(-lambda * T) = 1 - (1 - p1)^T
```

This converts the one-year probability to the actual funding horizon instead of using the one-year probability directly for a 30- or 90-day invoice. Constant intensity is an explicit simplifying assumption, not a claim that real buyer credit risk is time-invariant.

Convert the combined effective annual return budget to a continuous discount rate:

```text
b = ln(1 + a)
```

This prevents treating an effective annual percentage as though it were already a continuous rate.

## Cash-flow branches and advance

The model has two mutually exclusive branches:

1. With probability `1 - p(T)`, full face value `F` is collected at time `T`.
2. With probability `p(T)`, net recovery `R * P` is collected at time `T + L`.

All recoveries in the second branch are assigned to that common date. There is no integration over the actual default/recovery time distribution. Expected payment delay is also represented by one date, not a full delay distribution.

The expected NPV after the target funding/capital/margin return and upfront costs is:

```text
NPV = (1-p) * F * exp(-b*T)
    + p * R * P * exp(-b*(T+L))
    - P - C
```

Solve `NPV = 0` for the maximum advance:

```text
Pmax = ((1-p) * F * exp(-b*T) - C)
       / (1 - p * R * exp(-b*(T+L)))
```

The offer is rounded **down** to cents, leaving an NPV of zero or a small positive cent-rounding residual. A non-positive numerator, an advance below EUR 1, stale data or a rate above the supplied ceiling blocks financing. Rates are never silently clipped to satisfy policy. The UI's annual-rate ceiling is limited to 100% continuous, consistent with the existing future-value engine; that software boundary is not a market or legal assessment.

The report also displays `p * LGD * P` as an undiscounted expected principal credit loss. This is informative: it is **not subtracted a second time**, since the cash-flow branches already account for default losses.

## Annual rate, fee and future value

Once `P` is priced from the cash flows, calculate its annual continuous equivalent:

```text
r_percent = 100 * ln(F/P) / T
FV(t) = P * exp((r_percent/100) * t)
```

Thus `FV(T) = F` if full payment occurs on the assumed collection date. The gross invoice discount is `F - P`; its face-value percentage is saved for compatibility with existing loss scenarios. The discount is **not all net profit**: it covers credit losses, funding, costs and target return. Do not add the discount to the exponential return again.

`FV` is a conditional/theoretical cash-flow curve, not the probability-weighted expected payoff. Extending the curve beyond the expected collection date does not change the invoice balance or establish contractual late-payment interest. A recorded actual simulated payment stops future-value accrual as in the existing engine.

For example, a EUR 15,000 invoice due in 45 days, with the explicitly fictional assumptions above, gives a 50-day funding horizon, an advance of EUR 14,835.65 and an annual continuous equivalent of approximately 8.0425%. This is a model example, not a recommended quote for a real buyer.

## Sensitivity and controls

The UI shows mechanical changes for doubled annual PD, LGD increased by ten percentage points, and 30 additional collection days. It reports both the newly affordable advance and the expected NPV **at the original advance**. A negative stressed NPV means the original offer misses the stated cost/return budget; it is not necessarily a negative nominal repayment.

At a fixed tenor, increasing PD, LGD or costs lowers the offer and raises its annual equivalent. Extending the tenor lowers the affordable advance when costs/risk apply, but need not raise the annual equivalent: a fixed euro upfront cost is annualised over a longer period. The model does not impose a false monotonic annual-rate rule across maturities.

Invoice confirmation, identity/documents declarations, future due date and the existing demo eligibility gate still apply independently of price. This pricing model never monetises a missing confirmation or overrides a dispute. The score gate itself is a prototype policy, not a validated PD threshold.

The quote is recomputed from the current invoice on save. SQLite optimistic version checks still reject stale writes. A successful funding records the full model version, inputs, source/date, invoice context, outputs and a reproducible SHA-256 report fingerprint. Existing risk-priced transactions retain their original annual rate and report. The fingerprint is not notarisation, proof that inputs are correct or a tamper-proof audit ledger.

## What is still required for real calibration

1. Define default, observation date, collection date and recovery cash-flow conventions consistently; distinguish lateness, dispute, fraud and insolvency.
2. Obtain suitably representative buyer-level default histories or a validated external one-year PD source. Assess sample size, censoring, selection effects, economic conditions, sector and out-of-time calibration. No arbitrary mapping from the current score to PD is acceptable.
3. Estimate nominal recovery fractions, collection costs and recovery timing from actual resolved cases, reconciling any already-discounted external LGD.
4. Calibrate collection-delay distributions and evaluate whether replacing them with a single expected date is adequate.
5. Measure actual funding, capital and servicing costs. Model concentration, dependence, wrong-way recourse risk, liquidity and uncertainty beyond the expected loss before relying on a target margin.
6. Backtest default calibration, recoveries and realised risk-adjusted profitability, set documented acceptance thresholds, and review data/model drift. This repository supplies deterministic mathematical and workflow tests, not evidence of empirical predictive validity.

## Design references

- [Bank of England, Modelling credit risk](https://www.bankofengland.co.uk/-/media/boe/files/ccbs/resources/modelling-credit-risk): default intensity, survival and horizon default probabilities.
- [EBA, Guidelines on loan origination and monitoring](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/credit-risk/guidelines-loan-origination-and-monitoring): costs, credit-risk-sensitive pricing, data and monitoring principles. These are design references, not a claim that the prototype implements the guidelines or is authorised for financial services.
