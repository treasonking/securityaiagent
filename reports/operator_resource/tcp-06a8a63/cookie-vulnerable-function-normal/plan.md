# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_48a68fe4b93d47fb9f0e18203f9e9756

Digest: 8b9fbb1ca034236387a7dbf195ee6fb8b96c54fc663dcfa96332c38906b3259b

Provider: mock; transport: function

Created/expires: 1793904430/1793904730; target: http://127.0.0.1:60912

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"operator-prepared-resources","revision":1,"snapshot_sha256":"53fed8d86b2e4801ea8af035cc0390409465a4125caaa3a844470f9e57140db7","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}}

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
