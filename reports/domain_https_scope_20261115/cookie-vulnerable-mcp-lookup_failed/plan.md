# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_0a7328ceed704a219894050a447f36cd

Digest: 2ac0915727a32e12f3afd09e5f3d2467a19ff802d371d3c61e8700b1ed6cd39f

Provider: mock; transport: mcp

Created/expires: 1794676200/1794676500; target: https://attachments.securityai.test:62938

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"98a779e9778bcd60ab11d87a3edf3bf5aa2792c856c9f088021c938bbc49d041","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-dns-san-v1","ca_bundle_sha256":"89f94ac6b63a8b9e3c482b5f5770f9c6f7697c0846c37a7e2afb53df893501a2","context_ca_sha256":"c9a8f931936f00a32a87a5d7a748c60c2a2baf8a5f1704e482d2b7f9084578d5","minimum_version":"TLSv1.2"},"domain":{"version":"domain-network-v1","allowed_ip_ranges":["127.0.0.1/32"],"allow_non_global":true,"resolver":"system-a-aaaa-all-v1","connection":"numeric-peer-checked-per-request-v1","hostname":"attachments.securityai.test","port":62938}}

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
