# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_6d6a2dd747484e8c8a983a3cd5000dff

Digest: 564e56d719d501b1b7e9515141437fce66d3223ce1140dac9a504db5220d47bd

Provider: mock; transport: function

Created/expires: 1794553914/1794554214; target: http://127.0.0.1:53826

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"d71ea9ab5c36d8b9f37aa123682ef5661876fc43cc44b5fba09dd751d6f1ae6b","effective_limits":{"max_requests":2,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0}}

Accounts/resources: {"user_a":{"principal_id":"member_K73","resource_id":"attachment_M4s8","proof_env":"OPERATOR_PROOF_A"},"user_b":{"principal_id":"member_R92","resource_id":"attachment_N9t2","proof_env":"OPERATOR_PROOF_B"}}

1. user-a: login /gateway/authenticate
2. user-b: login /gateway/authenticate
3. user-a: identity /gateway/session/profile
4. user-b: identity /gateway/session/profile
5. user-a: resource /workspace/attachments/attachment_M4s8
6. user-b: resource /workspace/attachments/attachment_N9t2
7. user-a: resource /workspace/attachments/attachment_N9t2
8. user-b: resource /workspace/attachments/attachment_N9t2
9. user-a: resource /workspace/attachments/attachment_M4s8
10. user-a: identity /gateway/session/profile
11. user-b: identity /gateway/session/profile
