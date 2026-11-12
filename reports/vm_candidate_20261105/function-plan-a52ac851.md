# Candidate execution preview

NOT_EXECUTED; review is not a vulnerability finding.

- Plan: plan_51d2d6a7e6fc494e9f285a80efe29416
- Digest: 326874f1f924d748a1a0247a6953629cfe5745932affba48cf4e10e358e1f71c
- Created / expires (Unix UTC seconds): 1793811678 / 1793811978
- Target: lab-web (http://10.78.0.30:8080); adapter: synthetic-records; auth: bearer
- Scenario: access-control-http; provider: mock; transport: function
- Accounts: user-a, user-b; login → own lists → private controls/cross-read/rechecks
- Routes: POST /api/session; GET /api/me/records; GET /api/records/{document_id}
- Expected normal usage: HTTP 9, tools 10 (not guaranteed)
- Worker maximum limits: {"max_requests":9,"max_tool_calls":10,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":2.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}
- Worker profile: lab-records-access-control r1
- Expected snapshot: 6a4d512a0681ddfba1939075f50dd133c4a180b7b5271ef6d751b0dc9e32dfe4
- Policy control: REST worker query, target HTTP 0; digest is not a signature.
