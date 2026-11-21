# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_4eb40dfbc25441289f48006c745e4a0a

Digest: e13c31edaf7c2d461ccdcb9e002150f79e4f432bdf9b51ec738f04a3cd33203e

Provider: mock; transport: function

Created/expires: 1794676203/1794676503; target: https://attachments.securityai.test:63022

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"b3ae7b05c79fd5bb8d6e1665e1139ec8fc4975b1a72bfaee8672e7c8a8517e13","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-dns-san-v1","ca_bundle_sha256":"263e6550e2f998dbdef0ae194bb927070ac8d850f8a77780021ed67f0e3eec1a","context_ca_sha256":"e123e7d54807a293feb3402be970e6cb5d7796b2d5ed673f17a822ef344c245a","minimum_version":"TLSv1.2"},"domain":{"version":"domain-network-v1","allowed_ip_ranges":["127.0.0.1/32"],"allow_non_global":true,"resolver":"system-a-aaaa-all-v1","connection":"numeric-peer-checked-per-request-v1","hostname":"attachments.securityai.test","port":63022}}

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
