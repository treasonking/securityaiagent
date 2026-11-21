# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_c9ec6665d1c946f3b1803ff2eb5939cd

Digest: 42c49874c1e3673690c629fc8fab51c05dbd2d31c11afed74c5653ae4b311f11

Provider: mock; transport: function

Created/expires: 1794676184/1794676484; target: https://attachments.securityai.test:62469

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"31d6137c9720ca18c83b3c360623c084efce0bee36933a93624e9e7faf1f4595","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-dns-san-v1","ca_bundle_sha256":"be1dc8a1eb84e68593aee506f20530bd8f158f8c16e68964198ad0bd415ffe6b","context_ca_sha256":"bd1cf7960eb034ccb83b1f3f24965bb462099ade913d72f042a0f7812b4b146d","minimum_version":"TLSv1.2"},"domain":{"version":"domain-network-v1","allowed_ip_ranges":["127.0.0.1/32"],"allow_non_global":true,"resolver":"system-a-aaaa-all-v1","connection":"numeric-peer-checked-per-request-v1","hostname":"attachments.securityai.test","port":62469}}

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
