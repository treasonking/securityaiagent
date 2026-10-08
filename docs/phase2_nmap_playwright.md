# Phase 2 gate: Nmap and Playwright

Nmap과 Playwright는 다음 조건을 모두 충족한 뒤 별도 변경으로 추가한다.

- Nmap: `nmap_inventory(target_id, profile_id)` allowlist, argument array, `shell=False`, single IP, explicit ports, timeout/output limits, no CIDR/arbitrary NSE/exploit/brute force.
- Playwright: one fresh context per run, concurrency 1, bounded pages, blocked service worker/download/popup, exact-origin checks for navigation/redirect/frame/script/image/XHR/WebSocket and OS egress deny.
- controller UI Playwright와 worker 공격 browser를 별도 role/environment로 운영.
- firewall/port changes, policy tests, evidence schema, reset oracle, positive/negative network checks를 동시에 갱신.

현재 상태는 `NOT_IMPLEMENTED`다.
