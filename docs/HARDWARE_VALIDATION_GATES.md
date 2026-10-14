# 🔬 EchoNode Physical Hardware Validation Gates

**Document ID:** `ECHONODE-DOC-HW-001`  
**Target Hardware:** Waveshare ESP32-S3-Touch-LCD-1.85 (ESP32-S3R8, 16MB Flash, 8MB PSRAM OPI)  
**Authoritative Firmware Revision:** `2b5595a02e604f3db2ea0768e925b42d137f848b` + MoodAudio Studio v1  
**Status Standard:** All physical hardware tests are tracked strictly as **`PENDING`** until executed on physical bench hardware and empirical evidence is recorded.

---

## ⚠️ Architectural Discipline: Software vs. Hardware Testing

Antigravity and the engineering team maintain strict architectural honesty:
- **Automated Software Tests:** ✅ **62/62 PASSED** (FastAPI API, yt-dlp pure extraction, FFmpeg DSP analysis, EBU R128 loudness matching, audio restoration modes, database adapters, storage abstractions, and Phase 5 QA gates).
- **Firmware Static & Compilation Verification:** ✅ **PASSED** (PlatformIO diagnostic and production build environments, pinout audit script `tools/audit_pin_mappings.py`, and partition table alignment tool `tools/check_partitions.py`).
- **Bench Diagnostic Tooling:** ✅ **READY** (Test tone generator `tools/generate_test_tones.py`, MicroSD benchmark CLI `tools/sd_card_verifier.py`, and on-board diagnostic firmware `hardware_diagnostics.cpp`).
- **Physical Bench Verification:** ⏳ **PENDING (4 / 4 Gates)** — Must be performed using physical test bench equipment (multimeter, micro-speakers, FAT32 SD card, serial console).

> [!IMPORTANT]
> A successful firmware compilation or unit test run **never** closes a physical hardware gate. Each gate below defines its specific equipment, wiring, procedure, safety directives, and pass/fail criteria.

---

## 📋 Hardware Gate Summary Matrix

| Gate ID | Title / Requirement | Target Subsystem | Safety Directives | Acceptance Status |
| :--- | :--- | :--- | :--- | :---: |
| **`TEST-HW-01`** | Battery Connector Polarity | MX1.25 2-Pin Battery Port | `RULE_POLARITY_CHECK` | ⏳ **PENDING** |
| **`TEST-HW-02`** | Dual Speaker & Audio Tone Sweep | Dual JST-PH 2.0 / PCM5101 DAC + Amp | `RULE_VOLUME_CEILING`, `RULE_I2S_MUTING` | ⏳ **PENDING** |
| **`TEST-HW-03`** | MicroSD Card Mounting & TCA9554 CS | SPI Bus (`14, 16, 17`) + TCA9554 `EXIO3` | `RULE_STORAGE_BOUNDARY` | ⏳ **PENDING** |
| **`TEST-HW-04`** | Repeated Playback Lifecycle & Memory Stability | ESP32-S3 Heap, PSRAM, DMA Buffers | `RULE_MUTUAL_EXCLUSION`, FSM Lifecycle | ⏳ **PENDING** |

---

## Gate 1: `TEST-HW-01` — Battery Connector Polarity

### 1. Specification & Context
- **Board Connector:** 2-pin MX1.25 connector mounted on the bottom side of the Waveshare ESP32-S3-Touch-LCD-1.85 PCB.
- **Battery Target:** Single-cell 3.7V Lithium-Polymer (e.g. KP 702635 600mAh or equivalent) with 2-pin MX1.25 plug.
- **Mandatory Directive:** `RULE_POLARITY_CHECK` (documented in `RULES.md` and `docs/wiring_guide.md`).
- **Failure Consequence:** Commercial LiPo cells frequently have positive (red) and negative (black) leads reversed relative to Waveshare silkscreen conventions. Connecting an inverted battery immediately destroys the onboard charge management IC and damages the ESP32-S3 power rail.

### 2. Test Equipment Required
- Digital Multimeter with fine probe tips (set to DC Volts, 20V scale).
- Disconnected battery cell under test (unattached to board).
- Waveshare ESP32-S3-Touch-LCD-1.85 board with high-magnification inspection light.
- Fine precision tweezers (for pin swap if inversion is detected).

### 3. Step-by-Step Procedure
1. **Isolation Check:** Ensure both the board and the battery are completely disconnected from any USB-C cable or external power supply before starting.
2. **Board Silkscreen Audit:** Visually locate the MX1.25 battery header on the board. Identify the printed `+` (V_BAT) and `-` (GND) silkscreen markings directly adjacent to the connector pins.
3. **Open-Circuit Voltage Verification:**
   - Connect the multimeter **RED (+)** probe to the battery plug's RED terminal.
   - Connect the multimeter **BLACK (-)** probe to the battery plug's BLACK terminal.
   - Measure open-circuit voltage. Confirm positive reading between $+3.65\text{V}$ and $+4.20\text{V}$. If the reading displays a negative sign (e.g. $-3.85\text{V}$), the battery manufacturer inverted the wire coloring!
4. **Physical Alignment Check:** Align the keyed notch of the battery plug with the MX1.25 connector receptacle. Confirm that the measured positive contact aligns strictly with the PCB silkscreen `+` pin, and the measured ground contact aligns with the PCB silkscreen `-` pin.
5. **Corrective Action (if inverted):** Gently depress the plastic terminal retention tongue using tweezers, extract the crimped pins, swap positions, reinsert into the housing until they click, and repeat step 3.
6. **Mating & Power-On:** Mate the connector only after independent verification is logged.

### 4. Pass / Fail Acceptance Criteria
- **PASS:** Battery plug positive contact aligns with PCB silkscreen `+` marking, negative contact aligns with `-`, and measured DC voltage is $+3.7\text{V}$ to $+4.2\text{V}$.
- **FAIL:** Silkscreen markings are contradictory, polarity is inverted without corrective pin repositioning, or short-circuit continuity exists between V_BAT and GND.
- **Current Status:** ⏳ **`PENDING`** *(Awaiting physical multimeter measurement on bench hardware)*.

---

## Gate 2: `TEST-HW-02` — Dual Speaker and Audio Tone Sweep

### 1. Specification & Context
- **DAC:** Texas Instruments PCM5101 3-Wire I2S Stereo DAC (`DIN=GPIO47`, `LRCK=GPIO38`, `BCK=GPIO48`).
- **Amplifier Topology:** Onboard stereo class-D amplifier fed by the PCM5101 line-level outputs. *Note: The PCM5101 DAC does not drive 8Ω speaker coils directly; it drives the onboard power amplifier.*
- **Speakers:** Dual 8 Ω 1W miniature speakers terminated with JST-PH 2.0 connectors.
- **Safety Directives:**
  - `RULE_VOLUME_CEILING`: Digital volume hard-capped at $\le 65\%$ (`HARD_MAX_VOLUME_LEVEL = 14 / 21`, $-6.0\text{ dBFS}$ max sample amplitude `16000`).
  - `RULE_I2S_MUTING`: I2S DMA buffers cleared and muted upon idle/stop to eliminate high-frequency hiss.

### 2. Test Equipment Required
- 2x 8 Ω miniature speakers with JST-PH 2.0 female leads.
- Waveshare ESP32-S3-Touch-LCD-1.85 board connected via USB-C to serial monitor at 115200 baud.
- Infrared non-contact thermometer or thermal camera probe.
- Firmware binary compiled under PlatformIO `[env:diagnostics]`.

### 3. Step-by-Step Procedure
1. **Pre-Power Inspection:** Inspect speaker wires and JST-PH 2.0 connectors for loose strands or accidental bridging before plugging into onboard speaker headers.
2. **Flash Diagnostic Suite:**
   ```bash
   cd firmware
   pio run -e diagnostics --target upload
   pio run -e diagnostics --target monitor
   ```
3. **Execution of Section [3/5] (I2S Hardware Tone Sweep):**
   - **Part A (440 Hz Reference):** Emits 1.5 seconds of balanced 440 Hz sine wave across both Left and Right speakers simultaneously.
   - **Part B (Stereo Channel Check):** Emits 1.0 second of 880 Hz tone on Left speaker only (Right muted), followed by 1.0 second of 880 Hz tone on Right speaker only (Left muted).
   - **Part C (Frequency Sweep):** Emits a logarithmic sweep from 100 Hz to 2000 Hz over 2.5 seconds.
4. **Acoustic & Thermal Monitoring:**
   - Listen for clear acoustic reproduction, absence of distortion, buzzing, or audio dropouts.
   - Verify distinct Left vs. Right physical stereo separation.
   - Measure temperature on the onboard audio amplifier IC during and after the sweep. Confirm $<45^\circ\text{C}$ (no thermal runaway).
5. **Idle Mute Verification:** Confirm complete acoustic silence after the sweep finishes (`i2s_zero_dma_buffer` and `i2s_driver_uninstall`).

### 4. Pass / Fail Acceptance Criteria
- **PASS:** Both Left and Right speakers produce clear tones, Left/Right channel separation is distinct, no digital clipping or dynamic distortion occurs at $\le 65\%$ volume, and the amplifier temperature remains within safe ambient limits.
- **FAIL:** Audio is distorted/inaudible, channel crosstalk occurs, clipping sags the 3.3V rail, or the amplifier overheats.
- **Current Status:** ⏳ **`PENDING`** *(Awaiting physical speaker attachment and bench frequency sweep run)*.

---

## Gate 3: `TEST-HW-03` — MicroSD Mounting and TCA9554 Chip Select

### 1. Specification & Context
- **Card Socket:** Onboard TF MicroSD slot connected to ESP32-S3 SPI bus (`SCK=GPIO14`, `MISO=GPIO16`, `MOSI=GPIO17`).
- **Chip Select Architecture:** Hardware Chip Select is **NOT** a direct ESP32-S3 GPIO. It is routed to **`EXIO3`** on the onboard **TCA9554** 8-bit I2C IO expander (`I2C address 0x20` on shared bus `SDA=GPIO11`, `SCL=GPIO10`).
- **Safety Directive:** `RULE_STORAGE_BOUNDARY`: MicroSD card must be $\le 32\text{ GB}$ formatted as **FAT32** with standard 32KB/64KB cluster allocation.

### 2. Test Equipment Required
- MicroSD card $\le 32\text{ GB}$ (SanDisk / Kingston Class 10 / UHS-I).
- Host workstation with `tools/sd_card_verifier.py`.
- Waveshare ESP32-S3-Touch-LCD-1.85 board with serial monitor at 115200 baud.

### 3. Step-by-Step Procedure
1. **Pre-Format Card on Host:**
   - Format MicroSD card as FAT32 on host PC.
   - Copy uncompressed test tones from `backend/downloads/` (`test_tone_440hz_ref.wav`, `test_stereo_channel_check.wav`) to root directory.
   - Verify card structure using CLI validator:
     ```bash
     python tools/sd_card_verifier.py /Volumes/<SD_MOUNT>
     ```
2. **Cold Insertion:** Insert the verified MicroSD card into the board's slot with power off.
3. **Boot Diagnostic Suite:**
   - Power board and monitor serial logs during Section `[4/5] MICROSD SPI BENCHMARK`.
   - Confirm TCA9554 I2C communication succeeds at `0x20`.
   - Confirm TCA9554 asserts `EXIO3` LOW to enable card SPI communication.
   - Confirm `SD.begin(-1, spi, 20000000, "/sd", 5)` succeeds at 20 MHz.
4. **Read & Benchmark Verification:**
   - Verify card reports capacity $\le 32768\text{ MB}$.
   - Open root directory `/` and list files.
   - Read 256 KB chunk from test audio file and calculate read throughput ($\text{KB/s}$).
5. **Negative Test (Missing Card Handling):**
   - Power down, remove MicroSD card, reboot.
   - Confirm firmware gracefully logs `[SD] ERROR: Card Mount Failed!` without system panic, infinite loop, or bus lockup.

### 4. Pass / Fail Acceptance Criteria
- **PASS:** TCA9554 successfully controls `EXIO3` CS, FAT32 filesystem mounts cleanly, directory listing enumerates audio files, read throughput exceeds 500 KB/s, and missing-card condition produces a graceful error.
- **FAIL:** I2C communication with TCA9554 fails, SPI initialization times out, card is not detected, or read throughput suffers periodic stalling.
- **Current Status:** ⏳ **`PENDING`** *(Awaiting physical card insertion into board socket)*.

---

## Gate 4: `TEST-HW-04` — Repeated Playback Lifecycle and Memory Stability

### 1. Specification & Context
- **Target Subsystem:** ESP32-S3 internal SRAM heap, external 8MB PSRAM (OPI), and DMA ring buffers.
- **Mandatory Directive:** `RULE_MUTUAL_EXCLUSION` and finite state machine (`state_machine.h`).
- **Lifecycle Sequence:**
  $$\text{LOCAL\_SD\_STARTING} \longrightarrow \text{LOCAL\_SD\_ACTIVE} \longrightarrow \text{LOCAL\_SD\_STOPPING} \longrightarrow \text{OFF}$$
  `ACTIVE_A -> mute audio -> stop stream -> destroy Audio decoder -> free heap/PSRAM -> clear pointers -> verify resources -> ACTIVE_B`
- **Integrity Requirement:** No static/global audio decoder instance. The `Audio` decoder must be allocated dynamically in `AudioManager::createSDDecoder()` and completely deallocated in `AudioManager::destroySDDecoder()`.

### 2. Test Equipment Required
- Waveshare ESP32-S3 board with verified FAT32 MicroSD card containing test audio.
- Host PC running automated serial monitor capture over USB-C CDC (`115200` baud).
- Firmware binary compiled under `[env:waveshare_esp32s3_round]`.

### 3. Step-by-Step Procedure
1. **Flash Production Firmware:**
   ```bash
   cd firmware
   pio run -e waveshare_esp32s3_round --target upload
   pio run -e waveshare_esp32s3_round --target monitor
   ```
2. **Baseline Snapshot Acquisition:**
   - Record baseline memory free statistics at boot:
     - `esp_get_free_internal_heap_size()`
     - `heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL)`
     - `esp_get_minimum_free_heap_size()`
     - `heap_caps_get_free_size(MALLOC_CAP_SPIRAM)`
3. **Repeated Playback Cycling (50 Cycles):**
   - Execute 50 automated start/stop transitions via test loop:
     - Trigger playback of test track (`transitionTo(SystemState::LOCAL_SD_ACTIVE)`).
     - Allow playback to run for 5 seconds.
     - Trigger track stop (`transitionTo(SystemState::OFF)`).
     - Wait 1 second in standby.
4. **Telemetry & Fragmentation Logging:**
   - Log memory metrics after every stop cycle:
     ```
     [MEM] Decoder Destroyed | Internal Heap: <free> B (Delta: <d> B) | PSRAM: <free> B (Delta: <d> B) | Largest Block: <lb> B
     ```
   - Track largest contiguous internal free block to detect heap fragmentation.
5. **Continuous Stress Run (30 Minutes):**
   - Run continuous playback for 30 consecutive minutes to verify DMA stability, check for brownout sags, and verify the `RULE_THERMAL_SHUTDOWN` inactivity timer.

### 4. Pass / Fail Acceptance Criteria
- **PASS:** After 50 complete start/stop cycles:
  - Net internal heap delta is $\le \pm 64$ bytes (zero cumulative memory leak).
  - External PSRAM delta is exactly 0 bytes.
  - Largest internal free block remains within $95\%$ of baseline (no fragmentation lockup).
  - Zero watchdog resets (`RTCWDT` or `TG0WDT`), zero I2S DMA underruns, and zero brownout events.
- **FAIL:** Memory progressively decreases with each cycle, decoder fails to deallocate, largest free block shrinks drastically, or CPU resets.
- **Current Status:** ⏳ **`PENDING`** *(Awaiting physical test execution on connected ESP32-S3)*.

---

## 📊 Summary Release Gate Status

```
[TEST-HW-01] Battery Connector Polarity          : ⏳ PENDING (Awaiting bench multimeter verification)
[TEST-HW-02] Dual Speaker & Audio Tone Sweep     : ⏳ PENDING (Awaiting 8-ohm micro-speaker attachment)
[TEST-HW-03] MicroSD Mounting & TCA9554 CS       : ⏳ PENDING (Awaiting physical FAT32 card insertion)
[TEST-HW-04] Repeated Playback Lifecycle Stability: ⏳ PENDING (Awaiting 50-cycle physical memory stress test)
---------------------------------------------------------------------------------------------------------
OVERALL PHYSICAL HARDWARE VERIFICATION STATUS    : ⏳ PENDING BENCH VALIDATION (Zero false PASS claims)
```
