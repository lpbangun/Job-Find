# Gaps before release

- Real model-host execution and provenance, then paired independent relevance evaluation.
- Broad adaptive source discovery, query planning and source-family diversity beyond initial seeds.
- Human/independent evaluation of factual entailment; an exact quote alone can still be misinterpreted.
- Expanded structured salary/geography normalization and language-aware requirements.
- More ATS adapters and dynamic application verification. Current JavaScript-only forms remain unverified.
- Persistent source cooldowns across processes/runs remain unimplemented. Managed-proxy requests now run in a spawn-isolated worker with a parent monotonic deadline covering startup, open/headers/body and result handoff; timeout terminates, escalates to kill and reaps the worker. Body limits, an 8 MB result-metadata cap, exact deployment allowlists, default TLS verification and no automatic redirects/retries remain enforced. OS process startup, scheduling, local-file operations and cleanup can add overhead beyond the configured timeout (cleanup waits up to 0.2 s before kill, then up to 1 s); this is not a hard real-time guarantee. Offline fixtures cover worker cleanup and deadline enforcement, not a hostile-network security certification.
- Direct transport is unchanged: DNS has a separate process wait, and socket timeouts/remaining-time checks cover portions of the wire path. Total deadlines for trickling response headers and chunked framing are not fully enforced or tested; do not claim fully hardened networking.
- RFC robots percent-encoding edge cases, hostile/oversized parser inputs and broader security tests.
- Durable work queue, resume/cancellation semantics and tenant isolation for an eventual hosted API.
- Independent 40-development / 20-held-out evaluation, recall/coverage and blinded preference comparison.
- GitHub checkpoint will use a separate branch in the existing Job-Find repository, preserving its original runtime. No merge or deployment is authorized by this checkpoint.

None of these are claimed complete by passing fixture tests.
