# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_353bc7e9b66a4a45b2e6e3061195c882

Digest: ea94522a35810a9f06063abd28805e5b1c77dfafad6c1cf0afb5717ca9a28f86

Provider: mock; transport: mcp

Created/expires: 1793904447/1793904747; target: http://127.0.0.1:61238

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"operator-prepared-resources","revision":1,"snapshot_sha256":"ef122e0c4d986d5cfd0d73106cdfa0b8d61de1d8615ea7999ebcc1d2d700d534","effective_limits":{"max_requests":2,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}}

Accounts/resources: {"user_a":{"principal_id":"alice-17","resource_id":"95a8a830-f123-4f62-b38b-004d428ecab1","proof_env":"OPERATOR_PROOF_A"},"user_b":{"principal_id":"2048","resource_id":"ticket_2048","proof_env":"OPERATOR_PROOF_B"}}

1. user-a: login /session
2. user-b: login /session
3. user-a: identity /me
4. user-b: identity /me
5. user-a: resource /tickets/95a8a830-f123-4f62-b38b-004d428ecab1
6. user-b: resource /tickets/ticket_2048
7. user-a: resource /tickets/ticket_2048
8. user-b: resource /tickets/ticket_2048
9. user-a: resource /tickets/95a8a830-f123-4f62-b38b-004d428ecab1
10. user-a: identity /me
11. user-b: identity /me
