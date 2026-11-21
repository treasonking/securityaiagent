# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_d9e51fe3397c44daa258f5b6d14f01a6

Digest: 79fc5f8938fcc7fc5f17db38cfceb232b08f0ed45825fb3bdea1c13efaa4a701

Provider: mock; transport: function

Created/expires: 1794637276/1794637576; target: https://127.0.0.1:54061

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"c47632a426347125e029764ec502b50e3c857877ad434989dc4e946056de3de3","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-ip-san-v1","ca_bundle_sha256":"d827d10175ea6e124e2dca2d541b736da01f7e4d0e701621dc95fe937ce0705b","context_ca_sha256":"88e04589959e10b20a63453815143406313d3e92e8f4501e4f2c8ab1f10ec59a","minimum_version":"TLSv1.2"}}

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
