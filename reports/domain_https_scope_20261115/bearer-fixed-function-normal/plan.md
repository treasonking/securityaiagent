# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_a6fcca4b1f5f49499dd7e5b987d290e7

Digest: b50568f611414834dc9b0211e55de9fdfc08c06a35e5599dc77bcc816ec6f202

Provider: mock; transport: function

Created/expires: 1794676191/1794676491; target: https://attachments.securityai.test:62610

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"90979d94bda79266bd80513146adc131cccf9ff23bc3f57f77b0fb3f0d5b05fc","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-dns-san-v1","ca_bundle_sha256":"06f62d997308ccd3c53bb03c668d011d7548d00102cd66b69bd06627c09f8410","context_ca_sha256":"cd83224218cd5009070ff4953f53217c1d1c458adbbbd292b8ad9cb5e2f0b760","minimum_version":"TLSv1.2"},"domain":{"version":"domain-network-v1","allowed_ip_ranges":["127.0.0.1/32"],"allow_non_global":true,"resolver":"system-a-aaaa-all-v1","connection":"numeric-peer-checked-per-request-v1","hostname":"attachments.securityai.test","port":62610}}

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
