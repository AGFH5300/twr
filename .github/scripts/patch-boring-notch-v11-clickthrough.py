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

            // The AppKit panel is always the full open-notch size (640x210),
            // even while SwiftUI draws only the small collapsed notch. A clear
            // NSPanel still receives mouse events, so its invisible area can
            // otherwise block Finder/Desktop and the app underneath.
            //
            // Keep the whole panel interactive only while something genuinely
            // uses the expanded footprint. In the normal closed state, enable
            // mouse handling only when the pointer is over the actual collapsed
            // notch; everywhere else becomes click-through.
            let expandedInteractionActive = viewModel.notchState == .open
                || coordinator.expandingView.show
                || coordinator.sneakPeek.show
                || viewModel.isBatteryPopoverActive
                || viewModel.isCameraExpanded
                || SharingStateManager.shared.preventNotchClose

            let shouldAcceptMouse = expandedInteractionActive
                || viewModel.isMouseHovering(position: mouse)

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

        // Reuse the existing lightweight in-process pointer watcher. This is
        // not shell polling and adds no second timer.
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
assert "coordinator.expandingView.show" in updated
assert "shouldAcceptMouse = expandedInteractionActive" in updated
print("Applied v11 transparent-window click-through patch")
