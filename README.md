# Project 1: Video Streaming with RTSP and RTP

### GitHub link for this project: <https://github.com/SmolFong/Video_Streaming_RSTP_RTP.git>

## Phase 1: Working on RtpPacket.py file:

- Byte 0: V (2 bit) | P (1 bit) | X (1 bit) | CC (4 bit)
- Byte 1: M (1 bit) | PT (7 bit)
- Byte 2-3: Sequence Number (16 bit)
- Byte 4-7: Timestamp (32 bit)
- Byte 8-11: SSRC (32 bit)

---

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

---

## Phase 3: Basic UDP Media Streaming & Compatibility Hotfixes:

### 1. Core Objectives Achieved
* **Baseline Streaming Implementation:** Successfully established streaming of MJPEG video payloads (`movie.Mjpeg`) over the UDP transport protocol (`socket.SOCK_DGRAM`) inside a sandboxed Python virtual environment (`venv`).
* **State Machine Integration:** Integrated graphical Tkinter user interface event triggers with the core RTSP client state transitions (`INIT` $\rightarrow$ `READY` $\rightarrow$ `PLAYING` $\rightarrow$ `INIT`).

### 2. Encountered Anomalies & Engineering Resolutions

#### A. Graphical Module Resolution on macOS
* **Symptom:** Terminal raised a critical `ModuleNotFoundError: No module named '_tkinter'` upon executing the launcher.
* **Root Cause:** Standard Python distributions compiled via Homebrew on macOS strip out the Tcl/Tk graphical engine dependencies by default to optimize package footprints.
* **Resolution:** Deployed the missing system-level graphics bindings using `brew install python-tk`, flushed out the stale virtual environment, and re-provisioned an isolated `venv` with updated `Pillow` dependencies.

#### B. Legitimate "Broken Pipe" Network Crash During Playback
* **Symptom:** Client threw an unhandled `BrokenPipeError: [Errno 32] Broken pipe` immediately upon triggering the `PLAY` sequence.
* **Root Cause:** The server experienced a fatal silent crash during the initial `SETUP` request processing. The legacy `ServerWorker.py` parsed incoming command headers using hardcoded single-space tokenizers (`.split(' ')`), expecting `client_port= 25000` (with a deliberate white-space) instead of the standard `client_port=25000` format. Additionally, network-standard CRLF (`\r\n`) delimiters broken line-indexing parameters.
* **Resolution:** Restructured the `sendRtspRequest` method in `Client.py` to use Unix line breaks (`\n`) and explicitly injected a trailing whitespace character immediately after the `client_port=` string key to satisfy the server's rigid parsing criteria.

#### C. Operating System Interception of UDP Disconnections
* **Symptom:** Closing a streaming session threw an unhandled `OSError: [Errno 57] Socket is not connected`.
* **Root Cause:** The media socket uses the connectionless UDP protocol, yet the legacy code executed a `shutdown()` call which is exclusively valid for connection-oriented TCP streams. The macOS kernel intercepted this invalid state and raised an OS fault.
* **Resolution:** Swapped out the unneeded `self.rtpSocket.shutdown(...)` instruction for a clean, non-blocking `self.rtpSocket.close()` handler within the `listenRtp` network loop.

#### D. Multi-Threaded Synchronization Deadlock (Race Condition)
* **Symptom:** Pressing `PAUSE` and subsequently hitting `PLAY` caused the video feed to freeze permanently.
* **Root Cause:** A critical race condition occurred where the media rendering thread (`listenRtp`) was spawned *prior* to the local clearing and resetting of the `self.playEvent` synchronization flag. The newly initialized thread evaluated the stale state flag (which still carried the active Pause signal) and terminated immediately. Furthermore, legacy `isSet()` invocations triggered deprecation failures on Python 3.13+.
* **Resolution:** Re-ordered the execution thread lifecycle to completely flush the sync state via `playEvent.clear()` *before* invoking `Thread(...).start()`. Simultaneously updated all flag evaluations to use the modern `is_set()` syntax.

---

## Phase 4: Server Architecture Refactoring via I/O Multiplexing: 

### 1. Core Objectives Achieved
* **Event-Driven Architecture Evolution:** Migrated the server's network core away from a heavy thread-per-client paradigm into a single-threaded, high-efficiency, event-driven network engine using the native `select` module.
* **Concurrent Multi-Client Orchestration:** Demonstrated multi-session streaming capability, where a single server core routed distinct, non-interfering media bitstreams to multiple clients running concurrently on different UDP ports (e.g., 25000, 25002, 25004).

### 2. Encountered Anomalies & Engineering Resolutions

#### A. Port Contention & Socket Binding Failures
* **Symptom:** Launching the client triggered socket binding exceptions (`Address already in use`) or immediate port-range syntax errors.
* **Root Cause:** Zombie Python processes from previous ungraceful termination runs remained trapped in the background, maintaining an active kernel lock on UDP port 25000. Alternatively, typographical runtime arguments exceeded the physical 16-bit boundaries of networking ports (0 - 65535).
* **Resolution:** Transitioned to clean testing ports (e.g., 25002) for temporary validation, and systematically audited active ports using `lsof -i UDP:25000` to locate the process PID, executing a hard `kill -9 <PID>` to clear out kernel deadlocks.

#### B. Ungraceful Tracebacks on Server Interruption
* **Symptom:** Terminating the server engine via `Ctrl+C` dumped messy `KeyboardInterrupt` stack traces into the administrative console.
* **Root Cause:** Standard Python interpreter reaction when an asynchronous interrupt signal (SIGINT) breaks a blocking system-level kernel poll like `select.select()`.
* **Resolution:** Wrapped the entire asynchronous event polling loop inside a rigorous `try...except KeyboardInterrupt` block. Integrated a `finally` block to execute a graceful server teardown, programmatically closing all open client file descriptors and releasing the active TCP socket bindings.

#### C. Transient Local Storage Removal Failures
* **Symptom:** Closing a client window before receiving any media frames produced a critical `FileNotFoundError` during teardown.
* **Root Cause:** If a client aborted execution early (e.g., due to port conflicts), the media loop never ran, leaving the disk storage empty without a cache frame file (`cache-*.jpg`). The teardown hook `os.remove()` would violently fail when trying to delete a non-existent file path.
* **Resolution:** Encapsulated the disk I/O wiping execution routine inside a safe `try...except OSError:` wrapper, instructing the client instance to silently bypass cache purges if no matching files exist on disk.

### 3. Repository Governance & Source Optimization
* **Vulnerability & Junk Filtering:** Formulated a local `.gitignore` manifest to permanently block the tracking of virtual environments (`venv/`), Python bytecode caches (`__pycache__/`), OS system artifacts (`.DS_Store`), and transient runtime JPEG image buffers (`cache-*.jpg`).
* **Index Refactoring:** Cleared out historic garbage tracking data by forcing a index-level purge using `git rm -r --cached .`, resulting in a lightweight, pure source code repository on GitHub.

---

## Phase 5 Summary: Media Fragmentation, Pacing & Dual TCP/UDP Streaming

### Core Implementation
- **Marker Bit Decoding:** Added a `marker()` method to `RtpPacket.py` to extract the end-of-frame indicator (bit 7 of byte 1) from the incoming RTP header.
- **Adaptive Transport Protocol Layer:** Upgraded `ServerWorker.py` to parse dynamic protocol selections (`RTP/UDP` vs `RTP/TCP`). Established a 4-byte big-endian length-prefixed stream framework for connection-oriented TCP transmission.
- **Client UI & Reassembly Engine:** Integrated resolution/protocol radio toggles (SD/UDP vs HD/TCP) into `Client.py`. Re-architected the `listenRtp` thread to accumulate multi-packet binary fragments into a sequential `bytearray` buffer, flushing it to the display engine only upon encountering `marker == 1`.
- **Stream Termination & EOF Safeguards:** Modified the media delivery loop to detect null pointer returns from the video parser gracefully, shutting down threads cleanly rather than freezing or spinning resources.

### Encountered Anomalies & Engineering Resolutions

#### A. High-Frequency UDP Packet Loss & Frame Corruption
- **Symptom:** Naive UDP fragmentation caused severe screen tearing, multicolored noise artifacts, or immediate thread lockups.
- **Root Cause:** Slicing large frames into chunks and blasting them consecutively overwhelmed the client OS network stack. Out-of-order delivery and dropped fragments corrupted the JPEG binary structure, causing Pillow to crash.
- **Resolution:** Implemented **Pacing** on the server by introducing a micro-delay (`time.sleep(0.0005)`) between fragment transmissions. Concurrently expanded the client's OS socket receive space (`socket.SO_RCVBUF`) to 1MB to prevent buffer overflow.

#### B. OS-Level MTU Limit Violations (Message Too Long)
- **Symptom:** Pushing large unfragmented HD frames over UDP threw sudden connection errors or socket exceptions on macOS.
- **Root Cause:** The macOS network kernel strictly blocks individual UDP datagram payloads that exceed the Maximum Transmission Unit (MTU) limit, triggering an instantaneous system fault.
- **Resolution:** Re-established strict 1400-byte chunk segmentation for the UDP lane while keeping the raw byte-stream approach for the TCP lane.

#### C. Fixed 5-Byte Header Parsing Overflow
- **Symptom:** The stream permanently froze at an identical time stamp across both UDP and TCP networks.
- **Root Cause:** `VideoStream.py` relied on a naive `read(5)` protocol. High-definition frames occasionally generated data payloads requiring 6 characters for length definition (e.g., $\ge$ 100,000 bytes). This caused the parser to ingest part of the frame length into the binary payload, misaligning the file offset and throwing an unhandled `ValueError`.
- **Resolution:** Patched `VideoStream.py` with a robust `try...except ValueError` block, translating parsing failures into an authentic, safe stream termination signal.

---

## Phase 6 Summary: Telemetry, Real-Time Observability & Dashboard Optimization

### Core Implementation
- **Real-Time Telemetry Dashboard:** Appended a dedicated tracking layer (`statLabel`) onto the bottom of the Client GUI to display live network metrics, implementing modern observability principles.
- **Instantaneous Bounded Windowing (Data Rate):** Advanced the tracking architecture from a cumulative average calculation to a rolling **Time Window (0.5-second interval)** mechanism. This captures rapid fluctuations in throughput rather than smoothing them out over time.
- **Dynamic Metric Scaling (MB/s):** Refactored raw byte counters into Megabytes per second (`MB/s`) using binary scaling factor relations ($1 \text{ MB} = 1024 \times 1024 \text{ bytes}$). This heavily cleans up the UI footprint and matches commercial media player standards.
- **Packet Loss Accumulator:** Engineered a background packet-loss tracking logic using expected sequence number steps against the total packet ingestion count:
  $$\text{Loss Rate (\%)} = 100 \times \left(1 - \frac{\text{Actual Packets Received}}{\text{Last Sequence} - \text{First Sequence} + 1}\right)$$

### Encountered Anomalies & Engineering Resolutions

#### A. Graphical Thread-Safety Collisions on macOS
- **Symptom:** The metrics display froze indefinitely on the initial `"Waiting for stream..."` string placeholder, despite the media streaming smoothly in the background.
- **Root Cause:** Tkinter UI bindings are fundamentally single-threaded. When the background streaming worker thread (`listenRtp`) attempted to directly manipulate the `Label` text property, the macOS graphical kernel silently rejected the unauthorized cross-thread operation.
- **Resolution:** Implemented an asynchronous callback delegation loop using `self.master.after(0, ...)`. This pushes all visual updates back into the main UI execution event loop, resolving thread-safety deadlocks.

#### B. Asynchronous Teardown Faults (Socket Not Connected)
- **Symptom:** Executing a `TEARDOWN` command occasionally threw a critical `OSError: [Errno 57] Socket is not connected` stack dump.
- **Root Cause:** If network jitter or early disconnects occurred under heavy packet rates, the client attempted to invoke `.shutdown(socket.SHUT_RDWR)` on an RTSP socket that the operating system kernel had already closed or un-bound.
- **Resolution:** Encapsulated the network socket teardown routine inside tight `try...except OSError:` wrappers. Coupled it with a `finally:` block ensuring that `.close()` fires regardless of intermediate state transitions.

#### C. State Alignment Synchronization Deadlocks
- **Symptom:** After integrating the windowed telemetry modules, the video playback loop refused to load frames, and subsequent window closing attempts caused the interface thread to lock up.
- **Root Cause:** During code merging, a critical section of the initialization logic inside `playMovie()` was inadvertently stripped out, leaving telemetry variables unallocated. Furthermore, the rendering calls (`self.updateMovie()`) were accidentally excluded during metric loop insertion, breaking the media path.
- **Resolution:** Re-aligned the state initialization blocks, guaranteeing that all telemetry fields (`statWindowBytes`, `statWindowStartTime`) cleanly reset upon every fresh `PLAY` invocation, and restored the sequential image rendering pipeline within the main network worker loop.

## Some other issues: 

* Due to strict macOS system policies that lock global package modifications and strip the default Python environment of the Tcl/Tk GUI framework, running the project directly caused fatal `ModuleNotFoundError` exceptions for `_tkinter` and `PIL`.
* To bypass these OS-level restrictions and safely resolve dependencies without corrupting the system's core architecture, establishing an isolated virtual environment (`venv`) became a mandatory requirement to proceed with the project.

- So whenever I need to start the Video streaming Server and Client, I must turn on the venv first using : **source venv/bin/activate**. 

