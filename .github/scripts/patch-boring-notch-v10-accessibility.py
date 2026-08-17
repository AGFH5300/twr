from pathlib import Path

path = Path("boringNotch/XPCHelperClient/XPCHelperClient.swift")
text = path.read_text()

if "import ApplicationServices" not in text:
    text = text.replace("import Cocoa\n", "import Cocoa\nimport ApplicationServices\n", 1)

start_marker = "    // MARK: - Accessibility\n"
end_marker = "    // MARK: - Keyboard Brightness\n"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("Accessibility section anchors not found")

replacement = '''    // MARK: - Accessibility\n\n    // Accessibility-sensitive event taps are created by the main boringNotch\n    // process, not by the XPC helper. Query and request TCC authorization in\n    // this process so the settings state matches the process that actually\n    // needs Accessibility access. The helper remains responsible only for\n    // brightness operations below.\n    nonisolated func requestAccessibilityAuthorization() {\n        let options = [\n            kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true\n        ] as CFDictionary\n        _ = AXIsProcessTrustedWithOptions(options)\n    }\n\n    nonisolated func isAccessibilityAuthorized() async -> Bool {\n        let result = AXIsProcessTrusted()\n        await MainActor.run {\n            notifyAuthorizationChange(result)\n        }\n        return result\n    }\n\n    nonisolated func ensureAccessibilityAuthorization(promptIfNeeded: Bool) async -> Bool {\n        var result = AXIsProcessTrusted()\n\n        if !result && promptIfNeeded {\n            requestAccessibilityAuthorization()\n            try? await Task.sleep(for: .milliseconds(500))\n            result = AXIsProcessTrusted()\n        }\n\n        await MainActor.run {\n            notifyAuthorizationChange(result)\n        }\n        return result\n    }\n\n'''

text = text[:start] + replacement + text[end:]
path.write_text(text)

# Assertions: the Accessibility status must now be checked in the main app,
# while the XPC connection remains available for brightness functionality.
updated = path.read_text()
assert "AXIsProcessTrusted()" in updated
assert "AXIsProcessTrustedWithOptions" in updated
assert "private let serviceName = \"theboringteam.boringnotch.BoringNotchXPCHelper\"" in updated
assert updated.count("// MARK: - Accessibility") == 1
print("Applied v10 main-process Accessibility patch")
