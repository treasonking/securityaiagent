# Candidate execution preview

NOT_EXECUTED; review is not a vulnerability finding.

- Plan: plan_42a8d295daea462b9e8f02ab7af556ed
- Digest: abf7e1ed8435d6bd24f62051ff8164def9c03b4c1a5042b5074f7542ce3eea17
- Created / expires (Unix UTC seconds): 1793469586 / 1793469886
- Target: lab-web (http://127.0.0.1:49938); adapter: synthetic-documents; auth: cookie
- Scenario: access-control-http; provider: mock; transport: function
- Accounts: user-a, user-b; login → own lists → private controls/cross-read/rechecks
- Routes: POST /login; GET /documents; GET /documents/{document_id}
- Expected normal usage: HTTP 9, tools 10 (not guaranteed)
- Worker maximum limits: {"max_requests":9,"max_tool_calls":10,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":2.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}
- Worker profile: lab-access-control r4
- Expected snapshot: 953c1915c603b423e3ef0b7101c31b92b1b4080f48c83921887da36639d1d43f
- Policy control: REST worker query, target HTTP 0; digest is not a signature.
