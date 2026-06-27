This chart shows `TCPInfo.NotsentBytes` (`tcpi_notsent_bytes`): the
amount of data sitting in the TCP send buffer that the application
has written but TCP has not yet put on the wire. This data is waiting
for the congestion window or the pacing rate to allow it to be sent.

In a bulk download test like ndt7, the server writes data as fast as
it can. High `NotsentBytes` is the expected state — it means the app
is keeping TCP loaded. Persistently low values are more interesting:
the sender cannot fill the socket buffer fast enough, which is a
sender-side bottleneck and means the measurement may underestimate
the network.
