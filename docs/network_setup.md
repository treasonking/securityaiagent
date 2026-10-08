# VM network setup and verification

This file records intended configuration; it is not evidence that the user's VirtualBox host or VMs were changed.

| VM | NICs | Address | Service |
|---|---|---|---|
| controller | NAT + `control-net` + Host-only `ui-net` | 10.77.0.10, 192.168.56.10 | UI/API 8000 |
| worker | `control-net` + `lab-net` | 10.77.0.20, 10.78.0.20 | worker/MCP 9000 |
| target | `lab-net` | 10.78.0.30 | target 8080 |

worker와 target에는 기본 gateway·외부 DNS·NAT를 두지 않는다. controller의 기본 route는 NAT NIC에만 둔다. 모든 VM에서 IPv4 forwarding을 끄며, IPv6를 쓰지 않으면 NIC와 firewall에서 일관되게 차단한다. bridged networking, port forwarding, shared folders, shared clipboard, drag-and-drop은 사용하지 않는다.

VM 콘솔에서 실제 NIC 이름을 확인한 후 방화벽을 적용한다. 아래 검증 결과를 run evidence로 별도 보존한다.

```bash
ip -br addr
ip route
sysctl net.ipv4.ip_forward
```

Required positive checks:

- controller → worker `10.77.0.20:9000`
- worker → target `10.78.0.30:8080`
- Windows Host-only address → controller `192.168.56.10:8000`

Required negative checks:

- controller → target direct connection fails
- worker and target external HTTP/DNS fail
- Windows host cannot directly reach worker/target lab services
- worker firewall counters show only the registered target port

한 외부 URL 실패만으로 격리 전체를 증명하지 않는다. route, forwarding, NIC type, firewall policy/counters, positive connectivity를 함께 수집해야 한다. 현재 저장소 작업에서는 이 검증을 실행하지 않았다.
