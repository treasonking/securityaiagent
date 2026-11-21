# Operator resource preview

NOT_EXECUTED; digest is identity, not a signature or human authentication.

Plan: opplan_bb52503ed7f24ddd88748358492650cf

Digest: fcc3e8daa11a53ed193492e352e4a33b760e10fe25a93373ac8b04fd9bccadd6

Provider: mock; transport: function

Created/expires: 1794637286/1794637586; target: https://127.0.0.1:54247

Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.

Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.

Worker scope: {"profile_id":"local-project-attachments","revision":1,"snapshot_sha256":"8ef962bc07f75cd3df6c472236aa72d48c5467dbd9a5c4b6491948d168160435","effective_limits":{"max_requests":11,"max_tool_calls":12,"timeout_seconds":5.0,"run_timeout_seconds":180.0,"max_response_bytes":65536,"requests_per_second":1000.0,"max_concurrency":1,"max_runs":100,"state_ttl_seconds":600.0},"tls":{"verification":"dedicated-ca-ip-san-v1","ca_bundle_sha256":"3948760cfdb1f37232f36a393f5d0c8c691836380c95da90a633274d4fa73f62","context_ca_sha256":"e3095488cde5621937a4b5cecf619870de06dc675e2509aeb43631780c33904f","minimum_version":"TLSv1.2"}}

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
