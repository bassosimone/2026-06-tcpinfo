This chart shows four round-trip time metrics over the duration of
the download test. All values are in milliseconds.

**RTT (smoothed)** — `TCPInfo.RTT` (`tcpi_rtt`) — is the kernel's
exponentially weighted moving average of observed round-trip times.
It reflects the current state of the path including queuing delay.

**MinRTT** — `TCPInfo.MinRTT` (`tcpi_min_rtt`) — is the minimum RTT
the kernel has ever observed on this connection. It approximates the
base propagation delay of the path (the RTT you'd see with no
queuing). It can only decrease over time.

**RTTVar** — `TCPInfo.RTTVar` (`tcpi_rttvar`) — is the kernel's
smoothed mean deviation of RTT (not a true variance), used to compute
retransmission timeouts. Low values indicate a stable path; spikes
suggest sudden changes in queuing or routing.

**BBR MinRTT** — `BBRInfo.MinRTT` (`bbr_min_rtt`) — is BBR's own
min-filtered RTT estimate with a ~10-second window. Usually matches
the kernel's MinRTT but can diverge when BBR's filter expires and it
re-probes (during ProbeRTT phase). When BBR MinRTT rises above the
kernel's MinRTT, it means the path's baseline latency has increased
since the connection started.

**What to look for:** the gap between RTT (smoothed) and MinRTT is a
lower bound on queuing delay — MinRTT itself may include standing
queues that never drained. A large, persistent gap means buffers
along the path are filling up. BBR bounds this gap only loosely
(up to ~2.4× MinRTT under some conditions).
