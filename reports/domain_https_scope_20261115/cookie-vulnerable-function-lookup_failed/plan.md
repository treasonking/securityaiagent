# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_2c88cc9fa8af4f0fb5337c44ce7981a9

Digest: cd30f9888683201eba76a041701d01b993d3e1d3dd080101662a7f9c67dcd3e8

Provider: mock; transport: function

Created/expires: 1794676199/1794676499; target: https://attachments.securityai.test:62904

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"7ea30628097ea67140814ad42ada7986ecd3a4b05eef1ef2f3623aeb86076a03","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-dns-san-v1","ca_bundle_sha256":"65dc1bd79a956ec49bd48e079ab4c1db16008df2a68123f9daa02c8660a359d1","context_ca_sha256":"3f5e73f094b26c40f25702eaed279e726a9c409dfe8294da87e559b2675c38fa","minimum_version":"TLSv1.2"},"domain":{"version":"domain-network-v1","allowed_ip_ranges":["127.0.0.1/32"],"allow_non_global":true,"resolver":"system-a-aaaa-all-v1","connection":"numeric-peer-checked-per-request-v1","hostname":"attachments.securityai.test","port":62904}}

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
