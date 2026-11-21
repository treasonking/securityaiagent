# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_e674da6ac226405d85128f1bd4391155

Digest: 78f5483cebc4fbc47f99d6937f7ec717ba448a8132168f21a6640d51783241fb

Provider: mock; transport: function

Created/expires: 1794637284/1794637584; target: https://127.0.0.1:54207

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"e38ffed89c5209cf73389f09c8dad33b921c797ab17a2c339e9842e482c2b5a6","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-ip-san-v1","ca_bundle_sha256":"53ff9b1b99b9321d313a5b3bdc252ec5ea9eeaa6bad2295f43a34c56ab9c8824","context_ca_sha256":"96d722b4bdc2b2cdb63016f8411054de5cdef6d9fb7ed841a0e3a9fcfc705109","minimum_version":"TLSv1.2"}}

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
