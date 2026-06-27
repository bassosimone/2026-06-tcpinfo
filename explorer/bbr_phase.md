This chart shows BBR's two gain multipliers over time. BBR controls
sending primarily through **pacing** (how fast to send) rather than
through the congestion window alone. The gains determine what BBR is
doing at each moment.

**PacingGain** — `BBRInfo.PacingGain / 256` (`bbr_pacing_gain`) —
multiplies BBR's bandwidth estimate to set the pacing rate. Values
above 1.0 mean BBR is sending faster than its current estimate
(probing for more bandwidth). Values below 1.0 mean it is
deliberately slowing down (draining queues).

**CwndGain** — `BBRInfo.CwndGain / 256` (`bbr_cwnd_gain`) —
multiplies the bandwidth-delay product (BDP) to set the congestion
window. In steady state (ProbeBW) it is 2.0, giving headroom for ACK
aggregation and pacing bursts. During ProbeRTT it drops to 1.0, and
the congestion window shrinks to allow BBR to re-measure the path's
true minimum RTT.

**BBR's state machine:**

| Value | PacingGain | CwndGain |
|-------|------------|----------|
| 2.89 | Startup | Startup |
| 2.00 | | ProbeBW |
| 1.25 | ProbeBW (probe up) | |
| 1.00 | ProbeBW (cruise) | ProbeRTT |
| 0.75 | ProbeBW (drain) | |
| 0.34 | Drain | |

A typical download starts in *Startup* (both gains at 2.89,
exponential ramp-up), transitions to *Drain* (pacing gain 0.34,
draining the queue built during startup), then enters *ProbeBW*
where it cycles the pacing gain through probe up (1.25), drain
(0.75), and cruise (1.0). Every ~10 seconds, it enters *ProbeRTT*
(cwnd gain 1.0, cwnd shrinks) to refresh its MinRTT estimate.

**Note:** in ProbeBW the gain cycle advances roughly once per RTT,
often much faster than the sampling interval. Sampled gain values
are aliased snapshots of the cycle, not its shape.
