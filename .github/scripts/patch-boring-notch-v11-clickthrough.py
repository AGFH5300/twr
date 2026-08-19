from pathlib import Path

path = Path("boringNotch/boringNotchApp.swift")
text = path.read_text()

anchor = '''    @MainActor
    private func handleFullscreenPointerTick() {
        guard fullscreenBehaviorEnabled else { return }

        let mouse = NSEvent.mouseLocation
'''

replacement = '''    @MainActor
    private func updateNormalMousePassthrough(mouse: NSPoint) {
        func update(window notchWindow: NSWindow, viewModel: BoringViewModel, screenUUID: String) {
            // Fullscreen visibility owns mouse-event routing while its screen is
            // suppressed/revealed. Do not fight that state here.
            let fullscreenOwnsMouseRouting = fullscreenBehaviorEnabled
                && (fullscreenStatusSnapshot[screenUUID] ?? false)
            if fullscreenOwnsMouseRouting { return }

            // When the notch is open, every visible control in the full 640x210
            // panel must remain interactive. When it is closed, only the actual
            // collapsed notch should capture pointer events; the transparent
            // remainder of the fixed-size panel must click through to Finder or
            // the app underneath.
            let shouldAcceptMouse: Bool
            if viewModel.notchState == .open
                || viewModel.fullscreenInteractionActive
                || SharingStateManager.shared.preventNotchClose
            {
                shouldAcceptMouse = true
            } else {
                shouldAcceptMouse = viewModel.isMouseHovering(position: mouse)
            }

            let shouldIgnore = !shouldAcceptMouse
            if notchWindow.ignoresMouseEvents != shouldIgnore {
                notchWindow.ignoresMouseEvents = shouldIgnore
            }
        }

        if Defaults[.showOnAllDisplays] {
            for (uuid, notchWindow) in windows {
                guard let viewModel = viewModels[uuid] else { continue }
                update(window: notchWindow, viewModel: viewModel, screenUUID: uuid)
            }
        } else if let notchWindow = window {
            let uuid = vm.screenUUID ?? coordinator.selectedScreenUUID
            update(window: notchWindow, viewModel: vm, screenUUID: uuid)
        }
    }

    @MainActor
    private func handleFullscreenPointerTick() {
        let mouse = NSEvent.mouseLocation

        // The same lightweight in-process pointer watcher used by the fullscreen
        // fix also prevents the transparent part of the fixed-size notch panel
        // from stealing clicks in normal Spaces.
        updateNormalMousePassthrough(mouse: mouse)

        guard fullscreenBehaviorEnabled else { return }
'''

if anchor not in text:
    raise SystemExit("v11 pointer-tick anchor not found")
text = text.replace(anchor, replacement, 1)

# When fullscreen exits, don't blindly force the whole fixed-size panel back to
# interactive. Immediately recompute normal click-through for the current mouse
# position so the desktop cannot be blocked for even one pointer tick.
anchor2 = '''                setFullscreenSuppressed(false, on: uuid, animated: false)
            }
        }
    }
'''
replacement2 = '''                setFullscreenSuppressed(false, on: uuid, animated: false)
                updateNormalMousePassthrough(mouse: NSEvent.mouseLocation)
            }
        }
    }
'''
if anchor2 not in text:
    raise SystemExit("v11 fullscreen-exit anchor not found")
text = text.replace(anchor2, replacement2, 1)

path.write_text(text)

updated = path.read_text()
assert "private func updateNormalMousePassthrough(mouse: NSPoint)" in updated
assert "updateNormalMousePassthrough(mouse: mouse)" in updated
assert "shouldAcceptMouse = viewModel.isMouseHovering(position: mouse)" in updated
print("Applied v11 transparent-window click-through patch")
