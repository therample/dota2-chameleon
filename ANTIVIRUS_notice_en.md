# Chameleon and Antivirus False Positives: An Honest Explanation

> **TL;DR:** `Chameleon.exe` contains no viruses. Antivirus warnings are false positives from heuristics — a well-known trait of every Python program packed into a single exe file. Below is a plain-language explanation of why this happens, plus a 5-minute way to verify everything yourself.

## First Things First

- **The program is open source.** All code lives in the repository: you can read it — or skip reading it and simply build the program yourself from source. That beats any developer's assurances.
- **It does exactly one thing:** builds a VPK archive with cosmetic mods for Dota 2. It doesn't inject into the game, doesn't touch game executables, installs nothing into your system, and everything it does is undone by deleting a single file.
- **The problem isn't Chameleon.** Millions of legitimate programs get this treatment: AutoHotkey, System Informer (formerly Process Hacker) and dozens of open-source utilities have been flagged for years — that doesn't make them malware.

## Why Antivirus Suspects the File (In Plain Words)

**1. "One file" means self-extraction.**
For the program to run without Python installed, the exe unpacks itself into a temporary folder on every launch and runs from there. The antivirus sees the behavior "a file unpacks and executes itself" — exactly what malicious droppers do. The behavior matches, not the content, but heuristics can't read intent.

**2. The file has no "passport".**
A digital signature is a file's passport: it proves who published the program and that it wasn't modified after signing. Certificates cost money, so this free project doesn't have one yet — and antiviruses treat unsigned files with default suspicion.

**3. Everything inside is compressed.**
The program's code is packed inside the exe, and the scanner can't read it. Some engines say so honestly in the detection name: `Suspect.Packed` — "packed, can't see inside." That's not "found a virus", it's "I don't know what's in there."

**4. The program modifies files of a popular game.**
"A third-party program writes into the Steam folder" is suspicious on its own. Even though Chameleon merely places a resource archive that can be deleted without a trace.

## How to Read a VirusTotal Result

Don't look at the number "how many engines complained" — look at **which** engines and **what** the detections are called:

| What you see | What it means |
|---|---|
| 1–5 engines, names like `Generic`, `Heur.*`, `Suspect.Packed`, `Wacapew` | A classic false positive: the reaction to "unsigned packed exe" |
| Detections from minor engines (Jiangmin, MaxSecureHost, Zillya...) while Defender, Kaspersky, ESET are clean | Also a false positive: minor engines flag everything |
| Dozens of engines, including Defender, Kaspersky, ESET, with a specific malware family name | That would be a bad sign — not the case with Chameleon |

## Verify It Yourself in 5 Minutes

1. **Run it without the exe.** Download the project, install dependencies (`pip install -r requirements.txt`), run `python run.py` — and the "what's inside the exe" question disappears.
2. **Build your own exe.** The ready-made build command is in the repository — a file built on your own computer contains, by definition, only what's in the sources.
3. **Look inside our exe.** A PyInstaller onefile archive can be opened with [pyinstxtractor](https://github.com/extremecoders-re/pyinstxtractor): you'll see bundled libraries and `.pyc` files that decompile back into readable Python. There is no hidden code — check yourself.
4. **Compare the checksum** against the value in the release notes:
   ```bat
   certutil -hashfile Chameleon.exe SHA256
   ```
5. **Run it through VirusTotal** and judge the detection names using the table above, not the headline number.

## How Exactly This File Was Built (Honest List)

- official PyInstaller with a standard build command — you can repeat it using the instructions in the repository and get the same thing;
- single file (onefile), **no UPX compression**, no third-party packers;
- no obfuscation: the code isn't hidden, interface resources sit inside as ordinary files;
- no digital signature yet (a paid certificate is planned), so some heuristics may grumble even at a perfectly clean file.

## If Your Antivirus Still Complains

1. Add the file to exclusions — or (most reliable) build the exe yourself from source.
2. Report the false positive to your vendor — it genuinely helps every user of the project:
   - Microsoft (Defender): <https://www.microsoft.com/en-us/wdsi/filesubmission>
   - Kaspersky: <https://opentip.kaspersky.com/>
   - ESET: <https://www.eset.com/int/false-positive-report/>
3. Technical background — the official PyInstaller documentation, section "Antivirus products": <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html>

## FAQ

**Is it a virus?**
No. The code is open and auditable, the program doesn't inject into the game and doesn't hide what it does. False detections are a side effect of packing Python applications into one file, not a sign of malware.

**Why does VirusTotal complain if the file is clean?**
VirusTotal is not a verdict — it's 70+ different scanners, including aggressive ones that flag anything unknown and unsigned. A few of those on a fresh exe is normal, not a danger signal.

**Does Chameleon send anything to the internet?**
All network behavior is visible in the open sources — it can be audited just like the rest of the code. The program contains no hidden encrypted modules.

**Why is there no signature?**
Certificates cost money and require identity verification. For a free open-source project that's a noticeable expense. Signing is on the roadmap — it will remove the SmartScreen warning and most of the heuristic grumbling.
