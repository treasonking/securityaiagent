# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_da9120ae4abe42d1a9ca4c5bce1ff314

Digest: 1afd3db9245d95d6705d18e9767d98dd29bcf2fe5a5cb28b8217a592ebf604d3

Provider: mock; transport: mcp

Created/expires: 1794637280/1794637580; target: https://127.0.0.1:54155

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"ba741234da39f9e413e685308476465f09176ee2e03f5649ee847e89b4a3db80","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-ip-san-v1","ca_bundle_sha256":"9a1545cd22efdf9d19a171899bdaeed24245df19ce9ea78292a159d7c8f64a13","context_ca_sha256":"c1b034653aaf2ea80ff8851d0c85d16fd9f41203a6016477a75ed7c660c9a294","minimum_version":"TLSv1.2"}}

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
