from pathlib import Path

app_path = Path("boringNotch/boringNotchApp.swift")
app = app_path.read_text()

# AppDelegate state for deterministic fullscreen visibility handling.
old = (
    "    private var windowScreenDidChangeObserver: Any?\n"
    "    private var dragDetectors: [String: DragDetector] = [:] // UUID -> DragDetector\n"
)
new = (
    "    private var windowScreenDidChangeObserver: Any?\n"
    "    private var fullscreenVisibilityCancellable: AnyCancellable?\n"
    "    private var fullscreenStatusSnapshot: [String: Bool] = [:]\n"
    "    private var fullscreenBehaviorEnabled: Bool = false\n"
    "    private var fullscreenRevealScreens: Set<String> = []\n"
    "    private var fullscreenPointerTimer: Timer?\n"
    "    private var fullscreenHideWorkItems: [String: DispatchWorkItem] = [:]\n"
    "    private var fullscreenRevealHideWorkItems: [String: DispatchWorkItem] = [:]\n"
    "    private var dragDetectors: [String: DragDetector] = [:] // UUID -> DragDetector\n"
)
if old not in app:
    raise SystemExit("AppDelegate property anchor not found")
app = app.replace(old, new, 1)

old = (
    "        MusicManager.shared.destroy()\n"
    "        cleanupDragDetectors()\n"
    "        cleanupWindows()\n"
    "        XPCHelperClient.shared.stopMonitoringAccessibilityAuthorization()\n"
)
new = (
    "        MusicManager.shared.destroy()\n"
    "        fullscreenPointerTimer?.invalidate()\n"
    "        fullscreenPointerTimer = nil\n"
    "        fullscreenHideWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenRevealHideWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenHideWorkItems.removeAll()\n"
    "        fullscreenRevealHideWorkItems.removeAll()\n"
    "        cleanupDragDetectors()\n"
    "        cleanupWindows()\n"
    "        XPCHelperClient.shared.stopMonitoringAccessibilityAuthorization()\n"
)
if old not in app:
    raise SystemExit("terminate anchor not found")
app = app.replace(old, new, 1)

marker_start = app.find("    private func cleanupDragDetectors() {")
marker_end = app.find("    private func setupDragDetectors()", marker_start)
if marker_start == -1 or marker_end == -1:
    raise SystemExit("drag-detector method anchor not found")
cleanup_block = app[marker_start:marker_end]

methods = r'''    @MainActor
    private func fullscreenTarget(for screenUUID: String) -> (NSWindow, BoringViewModel)? {
        if Defaults[.showOnAllDisplays] {
            guard let notchWindow = windows[screenUUID],
                  let viewModel = viewModels[screenUUID]
            else { return nil }
            return (notchWindow, viewModel)
        }

        let uuid = vm.screenUUID ?? coordinator.selectedScreenUUID
        guard uuid == screenUUID, let notchWindow = window else { return nil }
        return (notchWindow, vm)
    }

    private func distance(_ point: NSPoint, to frame: NSRect) -> CGFloat {
        let dx = max(frame.minX - point.x, max(0, point.x - frame.maxX))
        let dy = max(frame.minY - point.y, max(0, point.y - frame.maxY))
        return hypot(dx, dy)
    }

    private func screenNearestPointer(_ point: NSPoint) -> NSScreen? {
        // Do NOT use frame.contains(point) here. At the literal top edge the
        // cursor may equal frame.maxY, which is outside CGRect's half-open max
        // boundary. That was the reveal bug in v5/v6/v8.
        guard let screen = NSScreen.screens.min(by: {
            distance(point, to: $0.frame) < distance(point, to: $1.frame)
        }) else { return nil }

        return distance(point, to: screen.frame) <= 4 ? screen : nil
    }

    @MainActor
    private func setFullscreenSuppressed(_ suppressed: Bool, on screenUUID: String, animated: Bool) {
        guard let (notchWindow, viewModel) = fullscreenTarget(for: screenUUID) else { return }
        guard viewModel.fullscreenSuppressed != suppressed || notchWindow.ignoresMouseEvents != suppressed else { return }

        if suppressed {
            // Make the invisible overlay click-through immediately while the
            // visual spring continues to finish.
            notchWindow.ignoresMouseEvents = true
        } else {
            notchWindow.ignoresMouseEvents = false
            if !notchWindow.isVisible {
                notchWindow.orderFrontRegardless()
            }
        }

        if animated {
            withAnimation(.spring(response: 0.45, dampingFraction: 1.0, blendDuration: 0)) {
                viewModel.fullscreenSuppressed = suppressed
            }
        } else {
            var transaction = Transaction()
            transaction.disablesAnimations = true
            withTransaction(transaction) {
                viewModel.fullscreenSuppressed = suppressed
            }
        }

        print("[BN-v9] \(suppressed ? \"SUPPRESS\" : \"REVEAL\") screen=\(screenUUID) animated=\(animated)")
    }

    @MainActor
    private func hideFullscreenNotch(on screenUUID: String) {
        guard fullscreenBehaviorEnabled,
              (fullscreenStatusSnapshot[screenUUID] ?? false),
              !fullscreenRevealScreens.contains(screenUUID),
              let (_, viewModel) = fullscreenTarget(for: screenUUID)
        else { return }

        fullscreenHideWorkItems[screenUUID]?.cancel()
        fullscreenHideWorkItems.removeValue(forKey: screenUUID)

        if viewModel.notchState == .open {
            // First use Boring Notch's normal open -> closed animation.
            viewModel.close(force: true)

            let item = DispatchWorkItem { [weak self] in
                Task { @MainActor in
                    guard let self else { return }
                    self.fullscreenHideWorkItems.removeValue(forKey: screenUUID)
                    guard self.fullscreenBehaviorEnabled,
                          (self.fullscreenStatusSnapshot[screenUUID] ?? false),
                          !self.fullscreenRevealScreens.contains(screenUUID)
                    else { return }
                    self.setFullscreenSuppressed(true, on: screenUUID, animated: true)
                }
            }
            fullscreenHideWorkItems[screenUUID] = item
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.38, execute: item)
        } else {
            setFullscreenSuppressed(true, on: screenUUID, animated: true)
        }
    }

    @MainActor
    private func revealFullscreenNotch(on screenUUID: String, mouse: NSPoint) {
        guard fullscreenBehaviorEnabled,
              (fullscreenStatusSnapshot[screenUUID] ?? false)
        else { return }

        let wasRevealed = fullscreenRevealScreens.contains(screenUUID)
        fullscreenRevealScreens.insert(screenUUID)
        fullscreenHideWorkItems[screenUUID]?.cancel()
        fullscreenHideWorkItems.removeValue(forKey: screenUUID)
        fullscreenRevealHideWorkItems[screenUUID]?.cancel()
        fullscreenRevealHideWorkItems.removeValue(forKey: screenUUID)

        setFullscreenSuppressed(false, on: screenUUID, animated: true)

        if !wasRevealed {
            print("[BN-v9] TOP EDGE screen=\(screenUUID) mouse=(\(Int(mouse.x)),\(Int(mouse.y)))")
        }
    }

    @MainActor
    private func scheduleFullscreenRevealHide(on screenUUID: String) {
        guard fullscreenRevealHideWorkItems[screenUUID] == nil else { return }

        let item = DispatchWorkItem { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.fullscreenRevealHideWorkItems.removeValue(forKey: screenUUID)
                guard let (_, viewModel) = self.fullscreenTarget(for: screenUUID) else { return }

                let mouse = NSEvent.mouseLocation
                let screen = NSScreen.screen(withUUID: screenUUID)
                let distanceFromTop = screen.map { abs($0.frame.maxY - mouse.y) } ?? .greatestFiniteMagnitude
                let withinHorizontalBounds = screen.map {
                    mouse.x >= $0.frame.minX - 1 && mouse.x <= $0.frame.maxX + 1
                } ?? false

                if (withinHorizontalBounds && distanceFromTop <= 110)
                    || viewModel.fullscreenInteractionActive
                    || viewModel.notchState == .open
                    || viewModel.isMouseHovering(position: mouse)
                {
                    return
                }

                self.fullscreenRevealScreens.remove(screenUUID)
                self.hideFullscreenNotch(on: screenUUID)
            }
        }

        fullscreenRevealHideWorkItems[screenUUID] = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.42, execute: item)
    }

    @MainActor
    private func handleFullscreenPointerTick() {
        guard fullscreenBehaviorEnabled else { return }

        let mouse = NSEvent.mouseLocation
        guard let pointerScreen = screenNearestPointer(mouse),
              let uuid = pointerScreen.displayUUID,
              (fullscreenStatusSnapshot[uuid] ?? false)
        else {
            return
        }

        let distanceFromTop = abs(pointerScreen.frame.maxY - mouse.y)
        let withinHorizontalBounds = mouse.x >= pointerScreen.frame.minX - 1
            && mouse.x <= pointerScreen.frame.maxX + 1

        if withinHorizontalBounds && distanceFromTop <= 12 {
            revealFullscreenNotch(on: uuid, mouse: mouse)
            return
        }

        guard fullscreenRevealScreens.contains(uuid) else { return }
        let viewModel = fullscreenTarget(for: uuid)?.1
        let keepVisible = (withinHorizontalBounds && distanceFromTop <= 110)
            || (viewModel?.fullscreenInteractionActive ?? false)
            || (viewModel?.notchState == .open)
            || (viewModel?.isMouseHovering(position: mouse) ?? false)

        if keepVisible {
            fullscreenRevealHideWorkItems[uuid]?.cancel()
            fullscreenRevealHideWorkItems.removeValue(forKey: uuid)
        } else {
            scheduleFullscreenRevealHide(on: uuid)
        }
    }

    @MainActor
    private func setupFullscreenPointerWatcher() {
        fullscreenPointerTimer?.invalidate()
        let timer = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.handleFullscreenPointerTick()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        fullscreenPointerTimer = timer
    }

    @MainActor
    private func applyFullscreenState(previous: [String: Bool]? = nil) {
        for screen in NSScreen.screens {
            guard let uuid = screen.displayUUID else { continue }
            let isFullscreen = fullscreenBehaviorEnabled
                && (fullscreenStatusSnapshot[uuid] ?? false)
            let wasFullscreen = previous?[uuid] ?? false

            if isFullscreen {
                if !wasFullscreen {
                    print("[BN-v9] FULLSCREEN ENTER screen=\(uuid)")
                }
                if fullscreenRevealScreens.contains(uuid) {
                    setFullscreenSuppressed(false, on: uuid, animated: true)
                } else {
                    hideFullscreenNotch(on: uuid)
                }
            } else {
                if wasFullscreen {
                    print("[BN-v9] FULLSCREEN EXIT screen=\(uuid)")
                }
                fullscreenRevealScreens.remove(uuid)
                fullscreenHideWorkItems[uuid]?.cancel()
                fullscreenRevealHideWorkItems[uuid]?.cancel()
                fullscreenHideWorkItems.removeValue(forKey: uuid)
                fullscreenRevealHideWorkItems.removeValue(forKey: uuid)

                // Restore without an animation on Space exit. This prevents the
                // misleading "animates in on the desktop" behavior from v7/v8.
                setFullscreenSuppressed(false, on: uuid, animated: false)
            }
        }
    }

'''
app = app[:marker_start] + cleanup_block + methods + app[marker_end:]

# Start the watcher and subscribe to the existing event-driven fullscreen detector.
old = "        setupDragDetectors()\n\n        if coordinator.firstLaunch {\n"
if old not in app:
    raise SystemExit("launch anchor not found")
launch = r'''        let fullscreenEnabledPublisher = Defaults
            .publisher(.hideNotchOption)
            .map(\.newValue)
            .map { $0 != .never }
            .removeDuplicates()

        fullscreenVisibilityCancellable = Publishers.CombineLatest(
            FullscreenMediaDetector.shared.$fullscreenStatus.removeDuplicates(),
            fullscreenEnabledPublisher
        )
        .receive(on: RunLoop.main)
        .sink { [weak self] fullscreenStatus, enabled in
            guard let self else { return }
            Task { @MainActor in
                let previous = self.fullscreenStatusSnapshot
                self.fullscreenStatusSnapshot = fullscreenStatus
                self.fullscreenBehaviorEnabled = enabled
                if !enabled {
                    self.fullscreenRevealScreens.removeAll()
                }
                self.applyFullscreenState(previous: previous)
            }
        }

        fullscreenStatusSnapshot = FullscreenMediaDetector.shared.fullscreenStatus
        fullscreenBehaviorEnabled = Defaults[.hideNotchOption] != .never
        setupFullscreenPointerWatcher()
        applyFullscreenState()

        setupDragDetectors()

        if coordinator.firstLaunch {
'''
app = app.replace(old, launch, 1)
app_path.write_text(app)

# View-model state. Leave the upstream fullscreen Space behavior intact; only
# suppress the SwiftUI notch visually. This preserves the window's ability to
# reside in Chrome's fullscreen Space, which the early build already proved.
vm_path = Path("boringNotch/models/BoringViewModel.swift")
vm = vm_path.read_text()

old = "    @Published var hideOnClosed: Bool = true\n\n    @Published var edgeAutoOpenActive: Bool = false\n"
new = (
    "    @Published var hideOnClosed: Bool = false\n"
    "    @Published var fullscreenSuppressed: Bool = false\n"
    "    @Published var fullscreenInteractionActive: Bool = false\n\n"
    "    @Published var edgeAutoOpenActive: Bool = false\n"
)
if old not in vm:
    raise SystemExit("view-model property anchor not found")
vm = vm.replace(old, new, 1)

# Disable the stock visual fullscreen hiding; AppDelegate now owns the exact
# collapse/reveal timing. Keep hideOnClosed false so revealing always restores
# the normal collapsed notch content.
old = (
    "            .sink { [weak self] shouldHide in\n"
    "                withAnimation(.smooth) {\n"
    "                    self?.hideOnClosed = shouldHide\n"
    "                }\n"
    "            }\n"
)
new = (
    "            .sink { [weak self] _ in\n"
    "                self?.hideOnClosed = false\n"
    "            }\n"
)
if old not in vm:
    raise SystemExit("fullscreen sink anchor not found")
vm = vm.replace(old, new, 1)

old = "    func open() {\n        self.notchSize = openNotchSize\n"
new = "    func open() {\n        guard !fullscreenSuppressed else { return }\n        self.notchSize = openNotchSize\n"
if old not in vm:
    raise SystemExit("open anchor not found")
vm = vm.replace(old, new, 1)

old = "    func close() {\n        // Do not close while a share picker or sharing service is active\n        if SharingStateManager.shared.preventNotchClose {\n            return\n        }\n"
new = "    func close(force: Bool = false) {\n        // Do not close while a share picker or sharing service is active unless\n        // fullscreen suppression explicitly needs to collapse the notch.\n        if !force && SharingStateManager.shared.preventNotchClose {\n            return\n        }\n"
if old not in vm:
    raise SystemExit("close anchor not found")
vm = vm.replace(old, new, 1)
vm_path.write_text(vm)

content_path = Path("boringNotch/ContentView.swift")
content = content_path.read_text()

old = '''                    .onHover { hovering in
                        handleHover(hovering)
                    }
'''
new = '''                    .onHover { hovering in
                        vm.fullscreenInteractionActive = hovering
                        handleHover(hovering)
                    }
'''
if old not in content:
    raise SystemExit("hover anchor not found")
content = content.replace(old, new, 1)

# Animate the entire notch into/out of the top edge. This is deliberately on the
# normal SwiftUI notch rather than alpha-hiding or ordering the NSPanel out.
old = '''        .frame(maxWidth: windowSize.width, maxHeight: windowSize.height, alignment: .top)
        .compositingGroup()
'''
new = '''        .frame(maxWidth: windowSize.width, maxHeight: windowSize.height, alignment: .top)
        .scaleEffect(x: 1, y: vm.fullscreenSuppressed ? 0.001 : 1, anchor: .top)
        .opacity(vm.fullscreenSuppressed ? 0 : 1)
        .animation(.spring(response: 0.45, dampingFraction: 1.0, blendDuration: 0), value: vm.fullscreenSuppressed)
        .compositingGroup()
'''
if old not in content:
    raise SystemExit("root frame anchor not found")
content = content.replace(old, new, 1)
content_path.write_text(content)

# Safety: do not touch BoringNotchSkyLightWindow collectionBehavior in v9.
window_path = Path("boringNotch/components/Notch/BoringNotchSkyLightWindow.swift")
window = window_path.read_text()
assert ".fullScreenAuxiliary" in window
assert ".canJoinAllSpaces" in window
assert "canJoinAllApplications" not in window

assert "screenNearestPointer" in app
assert "frame.contains(mouse)" not in methods
assert "fullscreenSuppressed" in vm
assert "close(force: Bool = false)" in vm
assert "value: vm.fullscreenSuppressed" in content
assert "orderOut" not in methods

print("v9 patch applied")
print("window collection behavior: pristine upstream")
print("top-edge screen selection: max-boundary safe")
print("fullscreen visual hide: native close then spring scale-to-top")
print("debug transition markers: [BN-v9]")
