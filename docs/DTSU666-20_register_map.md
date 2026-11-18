# DTSU666-20 register map

The DTSU666-20 is the dual channel DTSU666 that Sungrow sells with its
inverters: one set of voltage inputs, two sets of current inputs (CT1 on
terminals 1-9, CT2 on terminals 31-39) for 333 mV CTs or Rogowski coils.

Sources:

- Chint, *DTSU666 series three phase four wire electronic energy meter, User
  Manual*, ZTW0.464.0054 V1, Aug. 2024, table 8 (Modbus address table) and
  table 9 (device identification code). Copy:
  [`dtsu666-dual-channel-user-manual-en.pdf`](dtsu666-dual-channel-user-manual-en.pdf).
- Sungrow, *DTSU666-20 Quick Installation Guide*, DTSU666-20-QIEN-Ver13-202302
  (factory defaults: Modbus-RTU, address 1, 9600 bps, no parity, 1 stop bit).

All values are holding registers (function 0x03). Floats are IEEE 754, big
endian word and byte order (ABCD).

## Keyboard parameters (INT16)

| Address | Code     | Meaning                                                  | Integration key |
|---------|----------|----------------------------------------------------------|-----------------|
| 0x0000  | rEU      | Software version                                         | `rev`           |
| 0x0001  | UCode    | Programming code (1-9999)                                | `ucode`         |
| 0x0003  | nEt      | Wiring: 0 = 3P4W, 1 = 3P3W                               | `net`           |
| 0x0005  | E.SEt    | Total energy: 0 = sum of phases, 1 = algebraic (net) sum | `eset`          |
| 0x0006  | CT       | CT model 1-8 (CT01 100 A/333 mV ... RS04 4000 A/333 mV)  | `ct_type`       |
| 0x0007  | Pt       | Voltage transformer ratio x 0.1                          | `urat`          |
| 0x000A  | dISP     | Display rotation time (s)                                | -               |
| 0x000B  | b.LCd    | Backlight time (min)                                     | -               |
| 0x002B  | DeviceID | 0x03CS: C = channels, S = CT size (7 = 100 A, 8 = 250 A) | `device_id`     |
| 0x002C  | PtL1     | Port 1 protocol (0 Modbus, 1 DL/T645-2007)               | `protocol`      |
| 0x002D  | bPS1     | Port 1 baud (0 1200 ... 3 9600 ... 6 115200)             | `baud`          |
| 0x002E  | Adr1     | Port 1 Modbus address (1-247)                            | `addr`          |
| 0x0035  | SN_L     | Serial number, last four digits                          | device info     |
| 0x0036  | SN_M     | Serial number, middle four digits                        | device info     |
| 0x0037  | SN_F     | Serial number, first four digits                         | device info     |
| 0x0040  | PAr1     | Port 1 parity/stop (0 n.1, 1 n.2, 2 E.1, 3 O.1)          | -               |
| 0x0041-0x0044 | PtL2, PAr2, bPS2, Adr2 | Same for the second RS485 port         | -               |

0x0002, 0x0004, 0x0008-0x0009 and 0x002F-0x0034 are not documented, so the
integration never reads across them.

## Both channels, SI units (FLOAT32, "recommended")

Values are interleaved per quantity: channel 1, then channel 2.

| Address         | Channel 1          | Address         | Channel 2          | Unit |
|-----------------|--------------------|-----------------|--------------------|------|
| 0x3000-0x3004   | Uab1, Ubc1, Uca1   | 0x3006-0x300A   | Uab2, Ubc2, Uca2   | V    |
| 0x300C-0x3010   | Ua1, Ub1, Uc1      | 0x3012-0x3016   | Ua2, Ub2, Uc2      | V    |
| 0x3018-0x301C   | Ia1, Ib1, Ic1      | 0x301E-0x3022   | Ia2, Ib2, Ic2      | A    |
| 0x3024-0x302A   | Pt1, Pa1, Pb1, Pc1 | 0x302C-0x3032   | Pt2, Pa2, Pb2, Pc2 | W    |
| 0x3034-0x303A   | Qt1, Qa1, Qb1, Qc1 | 0x303C-0x3042   | Qt2, Qa2, Qb2, Qc2 | var  |
| 0x3044-0x304A   | St1, Sa1, Sb1, Sc1 | 0x304C-0x3052   | St2, Sa2, Sb2, Sc2 | ?    |
| 0x3054-0x305A   | PFt1, PFa1-PFc1    | 0x305C-0x3062   | PFt2, PFa2-PFc2    | -    |
| 0x3064-0x3068   | Angle A1-C1        | 0x306A-0x306E   | Angle A2-C2        | ?    |
| 0x3070          | Ft1                | 0x3072          | Ft2                | Hz   |

The manual describes St/Sa/Sb/Sc as power factor, although the power factors
proper are at 0x3054. Their real meaning (probably apparent power) is
unconfirmed, so the integration skips them, together with the phase angles.
It reads 0x3000 (68 registers) and 0x3054 (32 registers).

Channel 2 voltage and frequency are measured on the same inputs as channel 1,
so those sensors are created disabled.

## Energy (FLOAT32, kWh / kvarh)

| Channel 1 | Channel 2 | Values (ten floats per block)                                         |
|-----------|-----------|-----------------------------------------------------------------------|
| 0x101E    | 0x181E    | ImpEp, ImpEpA-C, NetImpEp, ExpEp, ExpEpA-C, NetExpEp                  |
| 0x1032    | 0x1832    | Q1Eq (quadrant I reactive energy)                                     |
| 0x103C    | 0x183C    | Q2Eq                                                                  |
| 0x1046    | 0x1846    | Q3Eq                                                                  |
| 0x1050    | 0x1850    | Q4Eq                                                                  |

## Legacy blocks (not used)

0x2000-0x2044 (channel 1) and 0x2800-0x2830 (channel 2) repeat the
measurements in the scaled DTSU666 format (x 0.1 V, x 0.001 A, x 0.1 W, ...).
The manual marks them "not recommended".
