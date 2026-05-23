# Project 1: Video Streaming with RTSP and RTP

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

### Phase 3: Basic UDP Media Streaming & Compatibility Hotfixes:

#### 1. Core Objectives Achieved
* **Baseline Streaming Implementation:** Successfully established streaming of MJPEG video payloads (`movie.Mjpeg`) over the UDP transport protocol (`socket.SOCK_DGRAM`) inside a sandboxed Python virtual environment (`venv`).
* **State Machine Integration:** Integrated graphical Tkinter user interface event triggers with the core RTSP client state transitions (`INIT` $\rightarrow$ `READY` $\rightarrow$ `PLAYING` $\rightarrow$ `INIT`).

#### 2. Encountered Anomalies & Engineering Resolutions

##### A. Graphical Module Resolution on macOS
* **Symptom:** Terminal raised a critical `ModuleNotFoundError: No module named '_tkinter'` upon executing the launcher.
* **Root Cause:** Standard Python distributions compiled via Homebrew on macOS strip out the Tcl/Tk graphical engine dependencies by default to optimize package footprints.
* **Resolution:** Deployed the missing system-level graphics bindings using `brew install python-tk`, flushed out the stale virtual environment, and re-provisioned an isolated `venv` with updated `Pillow` dependencies.

##### B. Legitimate "Broken Pipe" Network Crash During Playback
* **Symptom:** Client threw an unhandled `BrokenPipeError: [Errno 32] Broken pipe` immediately upon triggering the `PLAY` sequence.
* **Root Cause:** The server experienced a fatal silent crash during the initial `SETUP` request processing. The legacy `ServerWorker.py` parsed incoming command headers using hardcoded single-space tokenizers (`.split(' ')`), expecting `client_port= 25000` (with a deliberate white-space) instead of the standard `client_port=25000` format. Additionally, network-standard CRLF (`\r\n`) delimiters broken line-indexing parameters.
* **Resolution:** Restructured the `sendRtspRequest` method in `Client.py` to use Unix line breaks (`\n`) and explicitly injected a trailing whitespace character immediately after the `client_port=` string key to satisfy the server's rigid parsing criteria.

##### C. Operating System Interception of UDP Disconnections
* **Symptom:** Closing a streaming session threw an unhandled `OSError: [Errno 57] Socket is not connected`.
* **Root Cause:** The media socket uses the connectionless UDP protocol, yet the legacy code executed a `shutdown()` call which is exclusively valid for connection-oriented TCP streams. The macOS kernel intercepted this invalid state and raised an OS fault.
* **Resolution:** Swapped out the unneeded `self.rtpSocket.shutdown(...)` instruction for a clean, non-blocking `self.rtpSocket.close()` handler within the `listenRtp` network loop.

##### D. Multi-Threaded Synchronization Deadlock (Race Condition)
* **Symptom:** Pressing `PAUSE` and subsequently hitting `PLAY` caused the video feed to freeze permanently.
* **Root Cause:** A critical race condition occurred where the media rendering thread (`listenRtp`) was spawned *prior* to the local clearing and resetting of the `self.playEvent` synchronization flag. The newly initialized thread evaluated the stale state flag (which still carried the active Pause signal) and terminated immediately. Furthermore, legacy `isSet()` invocations triggered deprecation failures on Python 3.13+.
* **Resolution:** Re-ordered the execution thread lifecycle to completely flush the sync state via `playEvent.clear()` *before* invoking `Thread(...).start()`. Simultaneously updated all flag evaluations to use the modern `is_set()` syntax.

---

### Phase 4: Server Architecture Refactoring via I/O Multiplexing: 

#### 1. Core Objectives Achieved
* **Event-Driven Architecture Evolution:** Migrated the server's network core away from a heavy thread-per-client paradigm into a single-threaded, high-efficiency, event-driven network engine using the native `select` module.
* **Concurrent Multi-Client Orchestration:** Demonstrated multi-session streaming capability, where a single server core routed distinct, non-interfering media bitstreams to multiple clients running concurrently on different UDP ports (e.g., 25000, 25002, 25004).

#### 2. Encountered Anomalies & Engineering Resolutions

##### A. Port Contention & Socket Binding Failures
* **Symptom:** Launching the client triggered socket binding exceptions (`Address already in use`) or immediate port-range syntax errors.
* **Root Cause:** Zombie Python processes from previous ungraceful termination runs remained trapped in the background, maintaining an active kernel lock on UDP port 25000. Alternatively, typographical runtime arguments exceeded the physical 16-bit boundaries of networking ports (0 - 65535).
* **Resolution:** Transitioned to clean testing ports (e.g., 25002) for temporary validation, and systematically audited active ports using `lsof -i UDP:25000` to locate the process PID, executing a hard `kill -9 <PID>` to clear out kernel deadlocks.

##### B. Ungraceful Tracebacks on Server Interruption
* **Symptom:** Terminating the server engine via `Ctrl+C` dumped messy `KeyboardInterrupt` stack traces into the administrative console.
* **Root Cause:** Standard Python interpreter reaction when an asynchronous interrupt signal (SIGINT) breaks a blocking system-level kernel poll like `select.select()`.
* **Resolution:** Wrapped the entire asynchronous event polling loop inside a rigorous `try...except KeyboardInterrupt` block. Integrated a `finally` block to execute a graceful server teardown, programmatically closing all open client file descriptors and releasing the active TCP socket bindings.

##### C. Transient Local Storage Removal Failures
* **Symptom:** Closing a client window before receiving any media frames produced a critical `FileNotFoundError` during teardown.
* **Root Cause:** If a client aborted execution early (e.g., due to port conflicts), the media loop never ran, leaving the disk storage empty without a cache frame file (`cache-*.jpg`). The teardown hook `os.remove()` would violently fail when trying to delete a non-existent file path.
* **Resolution:** Encapsulated the disk I/O wiping execution routine inside a safe `try...except OSError:` wrapper, instructing the client instance to silently bypass cache purges if no matching files exist on disk.

#### 3. Repository Governance & Source Optimization
* **Vulnerability & Junk Filtering:** Formulated a local `.gitignore` manifest to permanently block the tracking of virtual environments (`venv/`), Python bytecode caches (`__pycache__/`), OS system artifacts (`.DS_Store`), and transient runtime JPEG image buffers (`cache-*.jpg`).
* **Index Refactoring:** Cleared out historic garbage tracking data by forcing a index-level purge using `git rm -r --cached .`, resulting in a lightweight, pure source code repository on GitHub.