This chart shows `TCPInfo.CAState` (`tcpi_ca_state`) over time. This
is the TCP stack's loss recovery state machine, which operates
independently of the congestion control algorithm (BBR, CUBIC, etc.).
It tells you whether the kernel is detecting and recovering from
packet loss at each moment.

| Value | State | Meaning |
|-------|-------|---------|
| 0 | Open | Normal, no loss detected |
| 1 | Disorder | Duplicate ACKs arriving, suspicious |
| 2 | CWR | Congestion window reduced (ECN response) |
| 3 | Recovery | Fast recovery (SACK-based) |
| 4 | Loss | RTO fired, severe loss |

In a healthy connection, the state stays at **Open** (0). Frequent
transitions to **Recovery** (3) indicate ongoing packet loss with
SACK-based recovery. **Loss** (4) is rare on modern Linux: RACK-TLP
(RFC 8985) repairs nearly all loss within Recovery, so reaching Loss
suggests a path blackout rather than ordinary congestion. This is a
raw gauge — brief Recovery episodes can fall between samples;
cross-check with TotalRetrans.
