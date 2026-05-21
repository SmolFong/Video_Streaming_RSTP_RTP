# Project 1: Video Streaming with RTSP and RTP

## Phase 1: Working on RtpPacket.py file:

- Byte 0: V (2 bit) | P (1 bit) | X (1 bit) | CC (4 bit)
- Byte 1: M (1 bit) | PT (7 bit)
- Byte 2-3: Sequence Number (16 bit)
- Byte 4-7: Timestamp (32 bit)
- Byte 8-11: SSRC (32 bit)

## Phase 2: Working on Client.py:

### Core Implementation
- **Control Channel:** Established reliable RTSP communication over TCP (`socket.SOCK_STREAM`).
- **State Machine:** Managed three core client states: `INIT`, `READY`, and `PLAYING`.
- **Media Socket:** Initialized a UDP socket (`socket.SOCK_DGRAM`) for RTP data on `SETUP` with a `0.5s` timeout.

### RTSP Protocol Specifications
- Every request increments the `CSeq` number and strictly ends with `\r\n\r\n`.
- **SETUP:** Sent in `INIT`. Includes the `Transport` header with the target UDP port. Transitions to `READY` upon `200 OK`.
- **PLAY:** Sent in `READY`. Includes the `Session` ID and triggers the `listenRtp` thread. Transitions to `PLAYING` upon `200 OK`.
- **PAUSE:** Sent in `PLAYING`. Stops the media rendering loop. Transitions back to `READY` upon `200 OK`.
- **TEARDOWN:** Sent to terminate the session. Closes active sockets and cleans up cache files. Resets to `INIT` upon `200 OK`.
