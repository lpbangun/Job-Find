# Gaps before release

- Verified served-model provenance and paired independent relevance evaluation. Development smoke missions now exercise genuine host-callback judgments, but served-model identity remains explicitly unknown.
- Broad adaptive source discovery, query planning and source-family diversity beyond initial seeds.
- Human/independent evaluation of factual entailment; an exact quote alone can still be misinterpreted.
- Expanded structured salary/geography normalization and language-aware requirements.
- More ATS adapters and dynamic application verification. Current JavaScript-only forms remain unverified.
- Persistent source cooldowns across processes/runs remain unimplemented. Direct and managed-proxy requests now run in a spawn-isolated worker with a parent monotonic deadline covering startup, DNS/direct connection or proxy open, headers/body and result handoff; timeout terminates, escalates to kill and reaps the worker. Body limits, an 8 MB result-metadata cap, exact proxy deployment allowlists, direct public-DNS pinning, default TLS verification and no automatic redirects/retries remain enforced. OS process startup, scheduling, local-file operations and cleanup can add overhead beyond the configured timeout (cleanup waits up to 0.2 s before kill, then up to 1 s); this is not a hard real-time guarantee. Offline fixtures cover worker cleanup and deadline enforcement, not a hostile-network security certification.
- Direct deadline tests exercise the real HTTP parser using socket pairs, including trickling headers, body and chunk extensions. DNS/connect/TLS are mocked blocking stages; real TLS interoperability and hostile-network security certification remain outstanding. Spawn-based transport requires an importable host entry point and a guarded main.
- RFC robots percent-encoding edge cases, hostile/oversized parser inputs and broader security tests.
- Durable work queue, resume/cancellation semantics and tenant isolation for an eventual hosted API.
- Independent 40-development / 20-held-out evaluation, recall/coverage and blinded preference comparison.
- GitHub checkpoint will use a separate branch in the existing Job-Find repository, preserving its original runtime. No merge or deployment is authorized by this checkpoint.

None of these are claimed complete by passing fixture tests.
