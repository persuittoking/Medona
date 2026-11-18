# OnaRadar — business model (hypotheses)

> **Everything below is an assumption for discussion, not a measured fact.** No price, cost or volume here comes
> from a contract, a tender or an official statistic. Real-world numbers belong in `docs/PITCH_FACTS.md` with a source.

## Who pays, who uses
- **Users** — patronage nurses, family doctors, OvaBMU specialists, department heads. They do not pay; the product
  must save them time (fewer phone calls, a clear list of who needs action today).
- **Customer (payer)** — whoever is accountable for maternal and newborn outcomes and holds the budget:
  1. **Ministry of Health** (national roll-out, integration with DMED);
  2. **Regional health departments** (a region pays for its districts, often as a pilot first);
  3. **Donors / development programmes** in maternal and child health (fund the pilot and validation).
- **Why they would pay** — fewer missed red cases, proof that alerts were acted on (audit + measurement), and
  aggregate visibility for managers without exposing patient data.

## Pricing hypotheses (to be tested in the pilot)
| Model | Unit | Hypothesis |
|---|---|---|
| A. Per polyclinic subscription | polyclinic / year | flat fee incl. hosting, support, model updates |
| B. Per region licence | region / year | volume price for all polyclinics of a region |
| C. Donor-funded pilot → government budget line | pilot district, then region | pilot free to the region, then A or B |

## Break-even sketch (ALL values are assumptions — replace with real quotes)
Variables, not facts: `P` = price per polyclinic per year, `C_fixed` = yearly fixed cost (team, hosting, security,
clinical review), `c_var` = yearly variable cost per polyclinic (support, onboarding, compute).

Break-even number of polyclinics: `N = C_fixed / (P - c_var)`.

| Scenario (assumption) | C_fixed per year | P per polyclinic | c_var per polyclinic | Break-even N |
|---|---|---|---|---|
| Lean (small team, shared hosting) | 60,000 USD | 1,200 USD | 300 USD | 67 |
| Base | 120,000 USD | 1,500 USD | 400 USD | 110 |
| Conservative (in-country certified hosting, 24/7 support) | 200,000 USD | 1,800 USD | 600 USD | 167 |

These rows only illustrate the formula; they are not market prices. The pilot must measure the real `c_var`
(onboarding and support time per polyclinic) and the payer's willingness to pay.

## What the pilot must prove (for the payer)
- Time from red alert to acknowledgement, and share of red alerts closed **with** a new measurement.
- Number of unreachable red cases found and resolved.
- Nurse / doctor time saved (today shown in the demo only as an estimate, "taxminiy").
- Clinician acceptance of the rules and the explanation text.
