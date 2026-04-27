# Severability Audit

One clarification first: the answer you labeled "correct" is not correct. It repeats the same legal error and also misstates the fiscal-year labels. October 1, 2025 through September 30, 2026 is entirely FY2026, not split between FY2025 and FY2026. That matters because it shows the KB has both a statutory-exception failure and a basic FY-mapping failure.

## Prompt Comparison Addendum

The app's live prompts and the KB prompts are not identical across the board.

### Supervisor comparison

The KB supervisor at [00-supervisor.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/agents/00-supervisor.txt:1) is a broad workflow prompt. It tells the system to read all agent files and "do the work" by default rather than explain. See [00-supervisor.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/agents/00-supervisor.txt:43).

The app supervisor at [eagle-plugin/agents/supervisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/supervisor/agent.md:1) is much more orchestration-focused. It has explicit routing rules and tells the supervisor to invoke specialists rather than answer specialist topics itself. Most importantly, for appropriations-law questions it says: "When user asks about appropriations law, funding rules, or fiscal year: immediately invoke `@financial-advisor`." See [supervisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/supervisor/agent.md:620).

Conclusion on supervisor prompts: the app supervisor is not the main source of the severability error. If anything, it is safer than the KB supervisor because it pushes fiscal-law questions to the financial specialist instead of letting the supervisor improvise.

### Financial comparison

The app financial-advisor prompt at [eagle-plugin/agents/financial-advisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/financial-advisor/agent.md:17) contains the same governing appropriations-law rule that appears in the KB financial prompt. It states:

- severable services are funded in the fiscal year rendered,
- they cannot be forward-funded,
- cross-FY severable service contracts use incremental funding,
- and this is "Layer 1 — Core Knowledge" that should "Never retrieve" and "Always apply."

See [financial-advisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/financial-advisor/agent.md:45).

That means the app's live financial prompt is already defective in the exact place that matters. Even if the KB had been perfect, the financial agent prompt itself would still bias the model toward the wrong answer.

### Bottom line

If the question is "are my app instructions bad, or are the KB financial instructions bad?", the answer is:

1. Your app supervisor instructions are not the main problem.
2. Your app financial instructions are bad on this issue.
3. The KB severability documents are also bad on this issue.
4. The failure is therefore a compound error: bad financial prompt plus bad retrieved severability documents.

## App Output Analysis

The exact application answer makes the failure chain clearer. The answer is not a fresh legal analysis. It is mostly a stitched synthesis of:

1. the live financial-advisor prompt,
2. the bad severability KB summary,
3. the bad bona-fide-needs KB summary,
4. and an overextended use of GAO B-321640.

### What came from the bad KB

These answer elements map directly to the retrieved severability summary:

- "Each fiscal year's services must be funded with that fiscal year's appropriation"
  matches [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:19).
- The GAO formulation "single undertaking or job" matches [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:79).
- The "short bridge exception" discussion matches the same document's bridge section. See [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:239).
- The bad example structure "help desk support" plus "you cannot obligate all 12 months from FY25 appropriations" matches [appropriations_law_time_bona_fide_needs.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_time_bona_fide_needs.txt:89).

Your app also surfaced duplicate citations at the end:

- `appropriations_law_cost_contract_funding.txt` appears twice
- `appropriations_law_severable_services.txt` appears twice

That strongly suggests retrieval weighting or post-retrieval citation assembly is not deduplicating repeated documents.

### What came from the live financial prompt

These answer elements map directly to the app's financial-advisor prompt:

- severable services are funded in the fiscal year rendered,
- they cannot be forward-funded,
- cross-FY severable services are handled through incremental funding,
- option periods are separate bona fide needs.

See [financial-advisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/financial-advisor/agent.md:49).

So even without the retrieved severability summary, the live financial prompt was already steering the model toward the wrong conclusion.

### What the model added on its own

The answer adds some connective prose that is not copied verbatim from any one file, such as:

- "that's where severability controls everything"
- the polished two-category structure
- the compliance-risk framing that ties the rule to ADA exposure

But that is packaging, not the source of the legal error. The core wrong rule came from prompt and KB, and the model merely organized it cleanly.

### Why GAO B-321640 was misused

The answer cites B-321640 as if it reinforces the broad proposition that severable services crossing fiscal years must be split by FY. That is not what B-321640 is about. In your prompt and corpus, B-321640 is tied to IDIQ minimums and bona fide need / parking-funds risk. See [financial-advisor/agent.md](/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents/financial-advisor/agent.md:66).

The model appears to have taken a real bona-fide-needs caution from B-321640 and used it to strengthen a different proposition already supplied by the bad severability documents. That is a secondary reasoning error, but it was enabled by the upstream materials.

### Refined ranking after seeing the app answer

1. Bad live financial-advisor prompt: highest confidence.
2. Bad severability / bona-fide-needs KB summaries: highest confidence and clearly echoed in the answer text.
3. Retrieval duplication and citation duplication: high confidence.
4. Model reasoning misuse of B-321640: medium confidence, but derivative rather than primary.

## A. Root Cause Diagnosis

1. Agent prompt error in [09-FINANCIAL](/Users/hoquemi/Desktop/KB/rh-eagle-2/agents/09-FINANCIAL.txt:23) is the most likely primary failure. It hard-codes as "core knowledge" that severable services are funded only in the FY rendered, says they "cannot forward-fund," and tells the model "Never retrieve them. Always apply them." See [09-FINANCIAL](/Users/hoquemi/Desktop/KB/rh-eagle-2/agents/09-FINANCIAL.txt:49).
2. KB content error in the retrieved severability files is the strongest secondary cause. The two retrieved files are identical copies and both state the wrong rule categorically: severable services "require incremental funding if contract crosses fiscal years" and "cannot obligate entire" amount from the first FY. See [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:18) and [duplicate copy](/Users/hoquemi/Desktop/KB/rh-eagle-2/compliance-strategist/regulatory-policies/appropriations_law_severable_services.txt:18).
3. Retrieval amplification is the third cause. Your retriever does not deduplicate by content; it keeps separate docs unless they share the same `document_id` or `s3_key`, so identical files under different paths can both rank and reinforce the same wrong rule. See [knowledge_tools.py](/Users/hoquemi/Desktop/sm_eagle/server/app/tools/knowledge_tools.py:1012) and [knowledge_tools.py](/Users/hoquemi/Desktop/sm_eagle/server/app/tools/knowledge_tools.py:1242).

Model reasoning is not the primary failure. Given those inputs, the model mostly did what it was told.

## B. Specific Evidence

The retrieved severability doc is not merely incomplete; it is affirmatively wrong. Its example says a contract from October 1, 2025 to September 30, 2026 "spans two fiscal years" and must use "FY2025 funds" for Oct-Dec 2025. That is false on its face. See [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:228). The same file also gives the model a ready-made template telling it to answer that severable services crossing FYs "require incremental funding." See [appropriations_law_severable_services.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_severable_services.txt:338).

The broader bona fide-needs summary repeats the same wrong example and also uses stale statutory citations like `41 U.S.C. § 254c`. See [appropriations_law_time_bona_fide_needs.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_time_bona_fide_needs.txt:89) and [appropriations_law_time_bona_fide_needs.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_time_bona_fide_needs.txt:177). The incremental-funding file adds another date error, claiming October 2025 to September 2026 "spans FY26 and FY27." See [appropriations_law_incremental_funding.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/appropriations_law_incremental_funding.txt:38).

At the same time, your corpus does contain the correct rule, but not in the files that were retrieved. [ACQuipedia_Appropriations_Financial_Mgmt.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-guidance/ACQuipedia_Appropriations_Financial_Mgmt.txt:101) correctly states that for civilian agencies including HHS/NIH, `41 U.S.C. 3902` permits obligating the full amount for up to one year of severable services crossing fiscal years. [Contract_Obligation_Timing_GAO_Guidance.txt](/Users/hoquemi/Desktop/KB/rh-eagle-2/financial-advisor/appropriations-law/Contract_Obligation_Timing_GAO_Guidance.txt:69) says the same thing and correctly describes it as a statutory exception to the bona fide needs rule.

So the system did not really have "the same documents" in any meaningful sense. The authoritative exception existed in the corpus, but the prompt and retrieved docs steered the model away from it.

### Faulty reasoning chain

1. Supervisor routes the question to financial analysis.
2. Financial agent applies "core knowledge" without retrieval override.
3. Retrieved severability docs confirm the same hard rule twice.
4. No retrieved authority squarely presents `41 U.S.C. 3902`.
5. Model maps "severable" to "year-by-year funding" and treats the bridge idea as the only exception.
6. It then fills in a canned example from the KB, including the FY-label mistake.

## C. Concrete Fixes

Use these prompt changes in `09-FINANCIAL`:

```text
Replace the current severable-services rule with:

- Severable services: absent a statutory exception, annual appropriations generally fund the bona fide need arising as services are rendered.
- Critical exception — civilian executive agencies: under 41 U.S.C. § 3902, a severable-services contract, order, or option that begins in one fiscal year and ends in the next, and does not exceed one year, may be fully obligated at the time of award/exercise/order from funds current for the first fiscal year.
- Critical exception — DoD: 10 U.S.C. § 3133.
- Before concluding that severable services must be funded year-by-year, always test whether 41 U.S.C. § 3902, 10 U.S.C. § 3133, or 41 U.S.C. § 3903 applies.
- When sources conflict, prefer: statute > FAR > GAO decision > agency deskbook > internal summary.
- Never state that severable services “must” be incrementally funded across fiscal years unless you have first ruled out those statutory authorities.
```

### KB fixes

- Rewrite both retrieved severability files to center `41 U.S.C. § 3902` and `FAR 37.106(b)`.
- Delete or rewrite the "short bridge exception" as a universal rule unless you can source it to agency-specific authority.
- Fix all FY examples so they use actual fiscal-year boundaries.
- Replace stale cites: `41 U.S.C. § 253l` can be retained only as historical codification; current cite is `41 U.S.C. § 3902`. `41 U.S.C. § 254c` should be updated to current codification where applicable.
- Add a short "Exception First" box to every bona-fide-needs summary.

### Retrieval fixes

- Deduplicate by normalized content hash or canonical authority, not just `s3_key`.
- Add legal-authority boosting: if query contains `severable`, `fiscal year`, `bona fide needs`, or `fund`, auto-fetch statute/FAR/GAO primary authority.
- Add contradiction detection: if one retrieved doc says "must incrementally fund," force retrieval of `41 U.S.C. § 3902` and `FAR 37.106`.
- Prefer primary sources over secondary summaries for appropriations-law questions.

### Guardrail

- Before any appropriations-law answer, require this checklist: agency type, appropriation type, severable/non-severable, exact period dates, whether the period begins in one FY and ends in the next, whether the period exceeds one year, and whether `3902/3133/3903` applies.

## D. Reference Answer

What the system should have said is:

Severability matters because, absent statutory authority, severable services are generally chargeable to the appropriation current when the services are rendered, while non-severable services may be fully funded when the need arises. But for civilian executive agencies such as HHS/NIH, `41 U.S.C. § 3902` is a statutory exception: if a severable-services contract/order/option begins in one fiscal year and ends in the next, and the period does not exceed one year, the agency may obligate the full amount from funds current for the first fiscal year. `FAR 37.106(b)` implements that rule.

A correct example would be: if HHS awards a severable help-desk contract on September 15, 2025 for performance from September 15, 2025 through September 14, 2026, FY2025 annual funds may fund the full 12 months under `41 U.S.C. § 3902`. By contrast, a performance period of October 1, 2025 through September 30, 2026 is entirely FY2026, so that is not a FY2025/FY2026 split example at all.

Sources:

- [41 U.S.C. § 3902](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title41-section3902)
- [FAR 37.106](https://www.acquisition.gov/far/37.106)
- [GAO B-317636](https://www.gao.gov/products/b-317636)
