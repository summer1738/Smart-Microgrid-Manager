# Microgrid prototype circuits

## Your parts (pin labels)

| Part | Pins on your module | How to wire (see sections below) |
|------|---------------------|----------------------------------|
| **DHT11** | **`+`**, **`out`**, **`-`** | `+` → 3.3 V, `-` → GND, `out` → GPIO + 10 kΩ pull-up to 3.3 V if needed |
| **Light module** (often sold near “BH1750”) | **`DO`**, **`GND`**, **`VCC`** | `VCC` → 3.3 V, `GND` → GND, `DO` → digital GPIO (not I2C SDA/SCL) |

**Diagrams in this folder:**

| File | Purpose |
|------|--------|
| **`esp32_doit_final_wiring.svg`** | **Source of truth** — vector schematic: ESP32 pin names, nets, and labels (open in a browser or Inkscape). |
| **`esp32_doit_final_silkscreen_diagram.png`** | PNG export of the SVG (same content as the schematic). |
| **`esp32_doit_breadboard_actual_components.png`** | **Illustration with recognizable parts** — breadboard-style view with DHT11, digital light module, LEDs, buzzers, NPN transistors, resistors, and jumper wires (for visual reference; match pins to the SVG). |

The schematic uses **3-pin DHT11** (`+`, `out`, `-`), **3-pin digital light** (`VCC`, `GND`, `DO`), **no physical switches** (`D18` / `D19` left unwired), LEDs, and transistor-driven buzzers with **color-coded** signal lines in the SVG.

Pin layout matches **your two columns of 15** as below.

---

## DOIT DevKit V1 — silkscreen on your board (15 + 15)

**One side (left when USB is toward you — confirm on your PCB):**

`VIN`, `GND`, `D13`, `D12`, `D14`, `D27`, `D26`, `D25`, `D33`, `D32`, `D35`, `D34`, `UN`, `UP`, `EN`

**Other side:**

`3V3`, `GND`, `D15`, `D2`, `D4`, `RX2`, `TX2`, `D5`, `D18`, `D19`, `D21`, `RXO`, `TXO`, `D22`, `D23`

| Silkscreen | Typical GPIO | Notes |
|------------|--------------|--------|
| `D13` … `D23` (where `D##` is printed) | GPIO **same number** as `##` | e.g. `D4` → **GPIO 4**, `D21` → **GPIO 21** |
| `RX2` | **GPIO 16** | UART2 RX (Arduino ESP32 core) |
| `TX2` | **GPIO 17** | UART2 TX |
| `RXO` | **GPIO 3** | UART0 RX (often labeled `RX0` on other boards) |
| `TXO` | **GPIO 1** | UART0 TX (often labeled `TX0`) |
| `UP` | **GPIO 36** | Sensor pin **VP** (input-only) |
| `UN` | **GPIO 39** | Sensor pin **VN** (input-only) |
| `D34`, `D35` | **GPIO 34**, **GPIO 35** | **Input-only** (no internal pull-up; not for driving LEDs) |

Power: `VIN` (5 V USB via regulator path), `3V3`, `GND` (two `GND` pads — use either). `EN` = reset/enable.

### This microgrid circuit — use **these** holes on your silkscreen

| Role | Connect here (your board) | Firmware GPIO |
|------|---------------------------|---------------|
| DHT11 `out` | **`D4`** | GPIO 4 |
| Light `DO` | **`D21`** | GPIO 21 |
| Switches (optional) → GND | **`D18`**, **`D19`** | GPIO 18, 19 — **omit** if not used |
| LED 1 | **`D25`** (+ 220 Ω) | GPIO 25 |
| LED 2 | **`D26`** (+ 220 Ω) | GPIO 26 |
| Buzzer 1 (via transistor) | **`D27`** | GPIO 27 |
| Buzzer 2 (via transistor) | **`D14`** | GPIO 14 |
| Sensors `+` / `VCC` | **`3V3`** | — |
| All `GND` / `-` | **`GND`** | — |

---

## Complete connections (updated checklist)

Use **`3V3`** and **`GND`** pads on the **same** column as in the silkscreen table above. Firmware pin numbers used in the **no-switches** build: **`D4`=GPIO4**, **`D21`=21**, **`D25`=25**, **`D26`=26**, **`D27`=27**, **`D14`=14**. (Add **`D18`/`D19`** only if you add physical switches.)

### DHT11 (three pins: `+`, `out`, `-`)

| DHT11 pin | ESP32 / breadboard |
|-----------|---------------------|
| `+` | **`3V3`** |
| `-` | **`GND`** |
| `out` | **`D4`** and **10 kΩ** from `out` to **`3V3`** (if the module has no pull-up) |

### Digital light sensor (three pins: `VCC`, `GND`, `DO`)

| Sensor pin | ESP32 / breadboard |
|------------|---------------------|
| `VCC` | **`3V3`** |
| `GND` | **`GND`** |
| `DO` | **`D21`** |

### Switches (optional — not in current diagram)

If you add **two-leg** pushbuttons: one leg to **`D18`** or **`D19`**, the other to **`GND`**; use **`INPUT_PULLUP`**. If you **omit** switches, leave **`D18`/`D19`** unconnected and set them to **`INPUT_PULLUP`** in firmware (reads HIGH) or do not use those pins.

### LEDs (220 Ω, respect anode / cathode)

| Signal | Path |
|--------|------|
| **LED1** | **`D25`** → **220 Ω** → **anode (+)** long leg → **cathode (−)** short leg → **`GND`** |
| **LED2** | **`D26`** → **220 Ω** → **anode (+)** → **cathode (−)** → **`GND`** |

### Buzzers (each: one **small NPN** transistor, one **1 kΩ** base resistor)

The examples use **2N2222**, but you can use **any similar NPN** in a **TO-92** (or SOT-23) package that can handle **~100 mA** or more on the collector (typical active buzzer). **Pin order differs by part** — use your transistor’s datasheet for **E / B / C**.

| Common substitute | Notes |
|-------------------|--------|
| **BC547** / **BC548** | Very common; same low-side buzzer circuit. |
| **2N3904** | Fine for this load. |
| **S8050** | Often in kits; check pinout (often E-B-C left-to-right facing the flat face). |

**If you have no transistor:** use a **buzzer module** that accepts a **3.3 V logic** input and has the driver onboard, **or** a **very quiet** piezo that draws only a **few milliamps** *might* work on a GPIO in a pinch (not ideal; risk to the ESP32 — prefer a transistor or module).

Per buzzer: **`3V3` → buzzer (+) → buzzer (−) → NPN collector**; **NPN emitter → `GND`**; **GPIO → 1 kΩ → NPN base**.

| Buzzer | GPIO → 1 kΩ → **base** | **Emitter** | **Collector** | Buzzer **(+)** | Buzzer **(−)** |
|--------|-------------------------|---------------|-----------------|----------------|----------------|
| **Buzzer 1** | **`D27`** | **`GND`** | to buzzer **(−)** | **`3V3`** | to **collector** |
| **Buzzer 2** | **`D14`** | **`GND`** | to buzzer **(−)** | **`3V3`** | to **collector** |

Wire your **actual** modules using the pinouts in the sections below if anything on the PCB differs from the drawing.

---

## DHT11 — three pins `(+, out, -)`

Typical bare DHT11:

| Pin | Connect to |
|-----|------------|
| `+` | ESP32 **3.3 V** (not 5 V unless your module says 5 V tolerant) |
| `out` | One GPIO (e.g. **GPIO 4**) |
| `-` | **GND** |

Add a **10 kΩ** resistor from **`out`** to **3.3 V** (pull-up) if your module does not already include it on the PCB.

Firmware expects a **single-wire** DHT11 on the chosen data pin (same idea as the diagram’s “DATA” line).

---

## Light sensor module — three pins `(DO, GND, VCC)`

Your module is labeled **DO**, **GND**, **VCC** (three pins only).

A **classic BH1750 breakout** uses **I2C** and normally has **SDA**, **SCL**, **VCC**, **GND** (four or more pins). A **three-pin** board with **DO** is often a **digital** light sensor (comparator output: light vs dark) or a different part, **not** I2C.

**Wiring for a 3-pin DO/GND/VCC module:**

| Pin  | Connect to        |
|------|-------------------|
| VCC  | **3.3 V**         |
| GND  | **GND**           |
| DO   | One GPIO (e.g. **GPIO 21** or any free input) — read as **digital HIGH/LOW** |

You do **not** need I2C pull-up resistors on SDA/SCL for this pinout; the backend code that talks to a **BH1750 over I2C** would need to be adapted if you use **DO-only** digital readings instead.

If your board is actually I2C but silkscreen is abbreviated, check the seller’s datasheet: some boards still expose **SDA/SCL** under different labels.

---

## LEDs — polarity (anode / cathode)

A through-hole LED has two legs:

| | Anode (**+**) | Cathode (**−**) |
|---|----------------|-----------------|
| **Leg length** | **Longer** leg | **Shorter** leg |
| **Plastic rim** | Often **round** on that side | **Flat** notch on the rim on that side |
| **Schematic sense** | Current enters here | Current exits here toward GND |

**Wiring for each LED load (D25 and D26):**

1. **GPIO** (`D25` or `D26`) → **220 Ω** resistor → **anode (+)** (long leg).
2. **Cathode (−)** (short leg) → **GND** (same GND as the ESP32).

If the LED does not light, it is often **inserted backwards** — flip it and try again (3.3 V through 220 Ω is safe for a standard indicator LED).

---

## Buzzers — types, polarity, and safe drive from the ESP32

### Active vs passive (important)

| Type | Behavior | ESP32 |
|------|----------|--------|
| **Active** buzzer | Has a **driver inside**; apply steady **DC** between **+** and **−** and it **beeps** at a fixed pitch. | Use **GPIO HIGH/LOW** through a **transistor** to turn sound on/off. Matches this project. |
| **Passive** buzzer | A **speaker-like** element; needs an **AC** signal (e.g. **PWM** or tone) to make different notes. | Does **not** match the simple “digital on/off” load in this diagram unless you add **tone/PWM** code. |

This wiring assumes **two active buzzers** with clear **+** and **−** (or a PCB marked **VCC** / **GND**).

### Why a transistor (not GPIO → buzzer directly)

- A typical active buzzer can draw on the order of **~30–100 mA** when on (check your part).
- ESP32 GPIOs are rated for only a **few tens of mA** per pin and are **not** meant to power inductive or noisy loads.
- An **NPN transistor** (e.g. **BC547**, **2N3904**, **S8050**, or **2N2222** if you have it) carries the buzzer current; the GPIO only supplies a **small base current** through the **1 kΩ** resistor.

### Polarity (**+** / **−**)

- **Through-hole cans:** usually **+** is marked on the top or longer lead; **−** is the other terminal.
- **Two-pin bare buzzer:** **+** → **3.3 V**, **−** → **NPN collector** (the **−** pin does **not** go straight to GND; the transistor connects it to GND when ON).
- **Three-pin modules** (**VCC**, **GND**, **SIG** / **IN**): follow the **seller’s diagram**—they may already include a transistor. Do not duplicate the circuit below unless your module is only a raw buzzer element.

**Wrong polarity** on many **active** buzzers: **no sound** or, in worst cases, **damage**. Match **+** to **3.3 V** and **−** to the **collector** as in the table.

### Standard circuit (one buzzer; duplicate for the second GPIO)

**Low-side NPN switch** (GPIO HIGH = buzzer ON):

| Node | Connect |
|------|---------|
| **3.3 V** (`3V3`) | **Buzzer +** (or module **VCC** if that is the positive supply pin) |
| **Buzzer −** | **NPN collector** |
| **NPN emitter** | **GND** (common with ESP32) |
| **GPIO** (`D27` or `D14`) | **1 kΩ** → **NPN base** |
| **NPN emitter** | **GND** (same as above) |

Current path when GPIO is **HIGH**: **3.3 V → buzzer + → buzzer − → collector → emitter → GND**.

- **Base resistor (1 kΩ):** limits base current so the GPIO is not overloaded.
- **One transistor per buzzer** so `D27` and `D14` are independent.

### Flyback diode (electromagnetic / coil-type buzzers)

If the buzzer is **electromagnetic** (internal coil), turning the transistor **off** quickly can produce a voltage spike on the collector. A **flyback diode** in **parallel with the buzzer**, **cathode (stripe) toward +** and **anode toward −**, protects the transistor.

- Many **small active piezo** buzzers do not need this; **open-frame electromagnetic** buzzers often do.
- If you are unsure, adding a **1N4007** or **1N4148** as above is safe when polarity matches the buzzer.

### Quick sanity check (before the ESP32)

With power **off**, you can sometimes verify polarity and that the part is **active**: momentarily connect **buzzer +** to **3.3 V** and **buzzer −** to **GND** (very briefly, correct polarity only). If it never beeps, check polarity or whether the part is **passive**. Prefer the **transistor circuit** for normal operation.

### Modules with a built-in transistor

Some buzzer **modules** only need **GND**, **VCC**, and **IN** / **SIG**. Read the module label: if **IN** expects a **3.3 V logic** signal, you may wire **IN** from GPIO through a resistor **only if** the datasheet says so. If the module already switches high current, you might **not** need an external transistor—follow that module’s diagram instead of the generic one above.

---

## Ground

Keep **one common GND** between ESP32, sensors, LEDs, and buzzer circuits.
