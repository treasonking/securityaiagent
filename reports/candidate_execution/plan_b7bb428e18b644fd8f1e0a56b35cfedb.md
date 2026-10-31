# Candidate execution preview

NOT_EXECUTED; review is not a vulnerability finding.

- Plan: plan_b7bb428e18b644fd8f1e0a56b35cfedb
- Digest: 3341909ad3855838b29353490a948c48c329c9526027a94d789c133036d2ed25
- Created / expires (Unix UTC seconds): 1793469605 / 1793469905
- Target: lab-web (http://127.0.0.1:50068); adapter: synthetic-documents; auth: cookie
- Scenario: access-control-http; provider: mock; transport: mcp
- Accounts: user-a, user-b; login → own lists → private controls/cross-read/rechecks
- Routes: POST /login; GET /documents; GET /documents/{document_id}
- Expected normal usage: HTTP 9, tools 10 (not guaranteed)
- Worker maximum limits: {"max_requests":9,"max_tool_calls":10,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":2.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}
- Worker profile: lab-access-control r4
- Expected snapshot: 9e7fd58626e67486e48864b704b4f51e49cc7d9238aa20d5f09b1034e0de9f12
- Policy control: REST worker query, target HTTP 0; digest is not a signature.
