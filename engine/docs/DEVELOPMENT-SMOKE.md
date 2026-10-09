# Development smoke evidence — 2026-10-09

These are small, selected-source integration probes, not a held-out benchmark or evidence that the 90% relevance release gate has been met. All applicant information was synthetic. No applications were submitted.

## Important correction

The first VTS shortlist was initially attributed to natural-language role-family names not expanding known aliases. That is a real general contract defect, now regression-tested, but it did **not** cause this particular shortlist: inspection of all 18 current VTS titles found no Software Engineer/Backend Developer title. All titles had zero engineering-alias retrieval score before and after normalization. The unchanged second run confirms no observed VTS yield improvement; it does not establish that no potentially suitable role exists among the unreviewed listings.

## Observations

1. VTS baseline: 18 listings collected, five reviewed, 13 outside the review budget. Two talent networks, two sales roles and an Engineering Manager were excluded. Zero qualified results against two requested; 11 genuine model calls; two network requests; no stage errors. Application verification was not reached.
2. VTS after family normalization: same prompt, synthetic profile, source and budgets. Same counts and exclusions, with 11 genuine model calls and zero qualified results. This was a development rerun, not an independent relevance evaluation.
3. 360Learning positive-path probe: explicitly selected after inspecting its two Software Engineer titles; the VTS employer restriction was removed while retaining the synthetic five-year backend engineer profile. 39 listings collected, five reviewed, 34 omitted by the budget. Two software roles were relevant but conditional because significant full-stack/interface experience was not established. Three other candidates were excluded. Both application checks remained unverified: a job-specific enabled form with exact job binding was not established. Zero qualified results against two requested; 11 genuine model calls; five network requests.

The third run exercised live collection, real structured extraction and semantic judgment, and conservative application verification. It did not demonstrate successful verified recommendations. Precision among qualified results is undefined when that set is empty; reporting it as 100% would hide the complete yield shortfall.

## Provenance and limitations

- The existing callback interface delivered genuine structured model judgments. The hosting runtime did not expose a served-model identifier; responses explicitly recorded `actual_model: "unknown"` and `served_model: null`. No configured identity was invented.
- Per-run source hashes, full callback request/response records, timestamps, source hashes and fetch/model receipts are retained locally in ignored run directories. The harness used finite callback deadlines, bounded calls/candidates/fetches and no paid search API.
- Raw run data and the local handoff harness are not published with the engine.
- Source selection was development-driven. Small candidate budgets leave substantial coverage unmeasured. The same judging workflow participated in multiple runs; these are not blinded independent judgments.
- Final acronym, spacing and mixed-family retrieval corrections are regression-tested. They were made around these development runs; each run's manifest identifies its actual source snapshot. No final-code broad live benchmark is claimed.
- Held-out profiles were not opened. Independent development-scale evaluation, implementation freeze, then a separate held-out evaluation remain necessary.

## Application verification diagnosis

Read-only inspection of the Spain Software Engineer application HTML found HTTP 200, the exact job title, no closed notice, and an application form with name/email controls. However, its visible “Submit application” control is a JavaScript `type="button"`; the only native submit is an unlabeled `hcaptchaSubmitBtn` with a hidden class. The form has neither an explicit action nor a recognized hidden job-ID field. The static verifier therefore cannot establish the required enabled, job-bound submission controls. This is a dynamic-form verification capability gap, not evidence that the posting is closed. No CAPTCHA was interacted with and nothing was submitted. The second posting had an HTTP 200 receipt but was not separately inspected for this diagnosis; its exact cause is not independently established.
