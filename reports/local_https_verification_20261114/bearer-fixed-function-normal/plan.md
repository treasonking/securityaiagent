# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_b1e521df0a9547dfabdccafae3089780

Digest: e9b0f4350ed4767ab2c8284b828148179f94f0896cd0588e9793e0985b3badb9

Provider: mock; transport: function

Created/expires: 1794637279/1794637579; target: https://127.0.0.1:54120

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"9f9dec78b6981e671380bdf5fd38dbbbcbe8550902f9766f6ff4a82edf7c2ce4","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-ip-san-v1","ca_bundle_sha256":"79296df0b8bb3bd56a1dd5efddc44c388755eeae1a404943411156feff416693","context_ca_sha256":"16331d56ff436f2e00e32c1d2182abb2a7b3112b6b7573a352b73111e55d0b4e","minimum_version":"TLSv1.2"}}

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
