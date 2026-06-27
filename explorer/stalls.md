This chart shows three cumulative time counters that answer the
question: *what prevented TCP from sending more data?* All values
are in milliseconds and increase monotonically over the test. The
slope of each line indicates how actively that bottleneck is limiting
throughput at each moment: a steep slope means it is active, a flat
slope means it is not.

**BusyTime** — `TCPInfo.BusyTime` (`tcpi_busy_time`) — cumulative
time the TCP send queue was non-empty (i.e., TCP had data to send).
If this tracks the wall-clock test duration, the application kept TCP
busy the entire time.

**RWndLimited** — `TCPInfo.RWndLimited` (`tcpi_rwnd_limited`) —
cumulative time TCP could not send because the receiver's advertised
window (RWND) was the tightest constraint. A large value means the
test measures the client rather than the network — throughput
underestimates the path.

**SndBufLimited** — `TCPInfo.SndBufLimited` (`tcpi_sndbuf_limited`)
— cumulative time TCP could not send because the local send buffer
was full. Treat large values as a hint of send-buffer pressure, not
a precise diagnosis — this counter instruments a narrow internal
condition.

**What to look for:** ideally, BusyTime matches the test duration
(app always has data), and RWndLimited and SndBufLimited are both
near zero (neither endpoint is the bottleneck, so the network is the
only limiting factor).
