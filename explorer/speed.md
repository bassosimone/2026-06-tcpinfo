This chart shows four different speed metrics over the duration of
the download test. All values are in megabits per second (Mbps).

**Avg Throughput (BytesAcked)** is computed as
`TCPInfo.BytesAcked × 8 / elapsed`, where elapsed is measured from
the first snapshot. This is the cumulative average throughput — total
acknowledged bytes divided by total time. It starts low (includes the
ramp-up) and converges toward the steady-state rate. Measured at the
TCP/IP level (includes WebSocket and TLS overhead).

**BBR BW** — `BBRInfo.BW × 8 / 1e6` (`bbr_bw`) — is BBR's
max-filtered estimate of the bottleneck bandwidth. BBR maintains this
as the highest delivery rate observed over a recent time window. It
represents what BBR *believes* the path can sustain. It is typically
higher than the average throughput because it captures the peak
capacity, not the average including ramp-up.

**Delivery Rate** — `TCPInfo.DeliveryRate × 8 / 1e6`
(`tcpi_delivery_rate`) — is the kernel's instantaneous estimate of
the rate at which data is being delivered to the receiver, computed
from the most recent ACK spacing. It oscillates as ACKs arrive in
bursts and is noisier than BBR BW (which is filtered).

**Pacing Rate** — `TCPInfo.PacingRate × 8 / 1e6`
(`tcpi_pacing_rate`) — is the rate at which the kernel is actually
clocking packets out. For BBR, this equals `PacingGain × BBR BW`.
When PacingGain is 1.25 (probe up), the pacing rate exceeds BBR BW.
When it is 0.75 (drain), the pacing rate drops below.

**What to look for:** in a healthy connection, Avg Throughput
converges to a stable value, BBR BW settles above it (representing
headroom), and Delivery Rate oscillates around the average. A large
gap between BBR BW and Avg Throughput may indicate that BBR is
overestimating the path capacity (e.g., due to a middlebox or PEP
buffering data).
