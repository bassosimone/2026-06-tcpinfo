TCP limits the amount of data in flight (sent but not yet
acknowledged) by two mechanisms: **congestion control** (CWND) limits
sending to avoid overwhelming the network, and **flow control**
(RWND) limits sending to avoid overwhelming the receiver. The actual
bytes in flight should never exceed `min(CWND, RWND)`.

**Kernel inflight** is the TCP stack's own computation of bytes
currently in flight:
`(Unacked - Sacked - Lost + Retrans) × SndMSS`, where
`Unacked` is total unacknowledged segments, `Sacked` are selectively
acknowledged (received but not yet cumulatively ACKed), `Lost` are
segments the kernel considers lost, and `Retrans` are
retransmissions currently on the wire. This matches the kernel's
internal `tcp_packets_in_flight()` function.

**SndCwnd × MSS** — `TCPInfo.SndCwnd × TCPInfo.SndMSS` — is the
congestion window in bytes. For BBR, this is set to approximately
`CwndGain × BDP` plus padding for TSO bursts and ACK aggregation.

**RWND** — `TCPInfo.SndWnd` (`tcpi_snd_wnd`) — is the receiver's
advertised window after scaling. It reflects how much buffer space
the receiver is willing to accept.

**What to look for:** the kernel inflight line should always stay at
or below both SndCwnd × MSS and RWND. When RWND is consistently
lower than CWND and close to the inflight, the receiver is the
bottleneck. When CWND is the tighter bound, the network (congestion)
is the limiting factor. On lossy paths, RWND below ~2× cwnd degrades
performance even when it doesn't appear to be the binding limit,
because loss recovery (SACK/PRR) needs sequence space beyond the
loss point.
