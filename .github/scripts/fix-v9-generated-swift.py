from pathlib import Path

path = Path("boringNotch/boringNotchApp.swift")
text = path.read_text()

bad = '        print("[BN-v9] \\(suppressed ? \\\"SUPPRESS\\\" : \\\"REVEAL\\\") screen=\\(screenUUID) animated=\\(animated)")\n'
replacement = (
    '        let debugAction = suppressed ? "SUPPRESS" : "REVEAL"\n'
    '        print("[BN-v9] \\(debugAction) screen=\\(screenUUID) animated=\\(animated)")\n'
)

if bad not in text:
    raise SystemExit("v9 debug print anchor not found")

text = text.replace(bad, replacement, 1)
path.write_text(text)
print("v9 generated Swift debug print fixed")
