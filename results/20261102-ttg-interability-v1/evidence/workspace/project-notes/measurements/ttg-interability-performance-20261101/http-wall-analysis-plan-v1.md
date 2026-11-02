# Primary HTTP wall and DB interval comparison

This is a post-capture read-only analysis plan. Candidate93ae77c7 and all
accepted borrowed execution/capture sources remain unchanged. No new benchmark
job is required. The final analysis will verify sealed inputs before reading
them and bind its own source/results alongside the accepted export.

## Actual recorded boundary

`reproduction/ttg-app-performance/workloads.py:109` implements the reused
`Server.post`. It creates the urllib Request, including JSON encoding, before
`start_ns`. The interval begins immediately before `urllib.request.urlopen`
and ends after `response.read()` and response-context exit. HTTP errors use
the same boundary around reading the error response. Stored `http_e2e_ms`
equals `(end_ns - start_ns) / 1e6`.

This client HTTP interval includes local transport, server request processing
and delivery of the full response body. It includes the effects of the primary
instrumentation. It excludes subsequent client JSON decoding, explicit drain
control, deferred trace serialization, client semantic assertions and the next
request's construction. Any native dispatch/context-close work that occurs
before response completion contributes to the actual interval; later work is
separate. The observer preserves native close/dispatch order and adds no
universal close wait.

The `post_response_drain` control runs only after `end_ns`, after client JSON
decoding. Request-attributed SQL may therefore complete after the HTTP response;
the accepted primary DB sum/union includes this work through the explicit drain
boundary. Report this scope next to HTTP wall instead of treating DB sum as a
subset of the HTTP interval. Use recorded dispatch/context-close timestamps
where available to show their actual relationship to the response boundary.

`wall_start` and `wall_end` are calendar-clock correlation fields. Derive elapsed
durations from monotonic `start_ns` and `end_ns`, not calendar-clock subtraction.

## Per-trial and n3 output

Join exact unique `(server_generation, request)` identities from sealed primary
`http-raw.jsonl` records to the existing per-RPC metrics. Reject missing,
duplicate, inconsistent or unsealed records. Select only `phase=workflow`.

For every actual primary RPC retain:

- Path/walker, native order, start/end and HTTP response wall milliseconds;
  cross-check the stored `http_e2e_ms` against the timestamps.
- Accepted all-role DB protocol sum/union, TOTAL/data/control SQL, foreground
  and background counts and actual PID/interval overlap.
- Explicit post-response drain fields and any request-attributed SQL interval
  finishing after HTTP end. Keep server-generation scope through restarts.

For the workflow report two distinct values:

1. **Summed primary HTTP response wall:** sum of actual business RPC intervals.
   Also retain their interval union and count. This is the main aggregate
   client-response metric for the existing sequential workflow.
2. **First-request start to last-response completion:** calendar span on the
   monotonic clock. It includes gaps between RPCs, such as prior explicit drain,
   client decoding/assertions and request construction. It is not continuous
   server processing time. A one-RPC traversal makes these values equal.

Report raw vectors and n3 median/min/max per fixture/mode for response-wall sum,
response span, accepted DB sum/union and SQL counts. Keep twelve excluded warmup
trials separate from the36 measured trials. All HTTP values are labelled
**primary instrumented HTTP**, derived from the same measured runs.

## Explanation of slow workflows

Use request-wall contributions to identify where application latency changes,
then inspect the matching SQL categories/fingerprints, actual overlap, recorded
process startup and lifecycle intervals. Preserve possible concurrency: summed
DB intervals may overlap, and request-attributed work may continue after response.
Wall time minus DB sum or union is not a foreground CPU measurement. Any CPU
claim requires independently valid CPU evidence with its own scope; a residual
duration remains an unattributed wall-time difference.

Add this table and concise boundary definitions to the final presentation after
capture/export. It supplements the accepted primary DB evidence and requires
neither a source mutation nor another timing run.
