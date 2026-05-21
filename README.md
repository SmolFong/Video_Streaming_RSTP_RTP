# Project 1: Video Streaming with RTSP and RTP

## Phase 1: Working on RtpPacket.py file:

- Byte 0: V (2 bit) | P (1 bit) | X (1 bit) | CC (4 bit)
- Byte 1: M (1 bit) | PT (7 bit)
- Byte 2-3: Sequence Number (16 bit)
- Byte 4-7: Timestamp (32 bit)
- Byte 8-11: SSRC (32 bit)

