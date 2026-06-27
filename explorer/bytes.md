This chart shows `TCPInfo.BytesAcked` (`tcpi_bytes_acked`) over
time, in megabytes. This is the cumulative count of bytes for which
the sender has received acknowledgment from the receiver. It only
counts original data, not retransmissions.

The slope of this curve is the throughput — the rate at which data is
being acknowledged. A steeper slope means faster transfer. A flat
segment would indicate a stall where no new data is being
acknowledged (e.g., during a retransmission timeout or severe loss
event).

Note: this is measured at the TCP/IP level and includes WebSocket and
TLS overhead. The true application-level bytes delivered would be
slightly less, but the ndt7 server does not record application-level
byte counts (`AppInfo` is null in server measurements).
