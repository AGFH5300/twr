from pathlib import Path

app_path = Path("boringNotch/boringNotchApp.swift")
app = app_path.read_text()

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
    "    private var fullscreenEntryHideWorkItems: [String: DispatchWorkItem] = [:]\n"
    "    private var fullscreenRevealHideWorkItems: [String: DispatchWorkItem] = [:]\n"
    "    private var fullscreenCollapseWorkItems: [String: DispatchWorkItem] = [:]\n"
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
    "        fullscreenEntryHideWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenRevealHideWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenCollapseWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenEntryHideWorkItems.removeAll()\n"
    "        fullscreenRevealHideWorkItems.removeAll()\n"
    "        fullscreenCollapseWorkItems.removeAll()\n"
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

    @MainActor
    private func revealFullscreenNotch(on screenUUID: String) {
        guard fullscreenBehaviorEnabled,
              (fullscreenStatusSnapshot[screenUUID] ?? false),
              let (notchWindow, viewModel) = fullscreenTarget(for: screenUUID)
        else { return }

        fullscreenRevealScreens.insert(screenUUID)
        fullscreenEntryHideWorkItems[screenUUID]?.cancel()
        fullscreenEntryHideWorkItems.removeValue(forKey: screenUUID)
        fullscreenRevealHideWorkItems[screenUUID]?.cancel()
        fullscreenRevealHideWorkItems.removeValue(forKey: screenUUID)
        fullscreenCollapseWorkItems[screenUUID]?.cancel()
        fullscreenCollapseWorkItems.removeValue(forKey: screenUUID)

        withAnimation(.spring(response: 0.38, dampingFraction: 0.88, blendDuration: 0)) {
            viewModel.hideOnClosed = false
        }
        notchWindow.ignoresMouseEvents = false

        // Keep the panel ordered in front. It is never ordered out in fullscreen.
        if !notchWindow.isVisible {
            notchWindow.orderFrontRegardless()
        }
    }

    @MainActor
    private func collapseFullscreenNotch(on screenUUID: String) {
        guard fullscreenBehaviorEnabled,
              (fullscreenStatusSnapshot[screenUUID] ?? false),
              !fullscreenRevealScreens.contains(screenUUID),
              let (notchWindow, viewModel) = fullscreenTarget(for: screenUUID)
        else { return }

        fullscreenCollapseWorkItems[screenUUID]?.cancel()

        // Stage 1: use Boring Notch's own normal open -> closed spring animation.
        if viewModel.notchState == .open {
            viewModel.close()

            let item = DispatchWorkItem { [weak self, weak viewModel] in
                Task { @MainActor in
                    guard let self, let viewModel else { return }
                    guard self.fullscreenBehaviorEnabled,
                          (self.fullscreenStatusSnapshot[screenUUID] ?? false),
                          !self.fullscreenRevealScreens.contains(screenUUID)
                    else { return }

                    // Stage 2: shrink the collapsed notch into the top edge using
                    // the same spring family as Boring Notch's close animation.
                    withAnimation(.spring(response: 0.45, dampingFraction: 1.0, blendDuration: 0)) {
                        viewModel.hideOnClosed = true
                    }
                    notchWindow.ignoresMouseEvents = true
                    self.fullscreenCollapseWorkItems.removeValue(forKey: screenUUID)
                }
            }
            fullscreenCollapseWorkItems[screenUUID] = item
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.34, execute: item)
        } else {
            withAnimation(.spring(response: 0.45, dampingFraction: 1.0, blendDuration: 0)) {
                viewModel.hideOnClosed = true
            }
            notchWindow.ignoresMouseEvents = true
        }
    }

    @MainActor
    private func scheduleFullscreenEntryHide(on screenUUID: String) {
        guard fullscreenEntryHideWorkItems[screenUUID] == nil else { return }

        let item = DispatchWorkItem { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                self.fullscreenEntryHideWorkItems.removeValue(forKey: screenUUID)
                guard self.fullscreenBehaviorEnabled,
                      (self.fullscreenStatusSnapshot[screenUUID] ?? false),
                      !self.fullscreenRevealScreens.contains(screenUUID)
                else { return }
                self.collapseFullscreenNotch(on: screenUUID)
            }
        }
        fullscreenEntryHideWorkItems[screenUUID] = item

        // Let the macOS fullscreen Space transition finish first. This makes the
        // collapse animation visible inside the fullscreen Space instead of being
        // swallowed by the Space transition.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.55, execute: item)
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
                let distanceFromTop = screen.map { max(0, $0.frame.maxY - mouse.y) } ?? .greatestFiniteMagnitude
                let stillInTopArea = distanceFromTop <= 100
                    && (screen?.frame.contains(mouse) ?? false)

                if stillInTopArea || viewModel.fullscreenInteractionActive || viewModel.notchState == .open {
                    return
                }

                self.fullscreenRevealScreens.remove(screenUUID)
                self.collapseFullscreenNotch(on: screenUUID)
            }
        }
        fullscreenRevealHideWorkItems[screenUUID] = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.40, execute: item)
    }

    @MainActor
    private func handleFullscreenPointerTick() {
        guard fullscreenBehaviorEnabled else { return }

        let mouse = NSEvent.mouseLocation
        let pointerScreen = NSScreen.screens.first(where: { $0.frame.contains(mouse) })
        let pointerUUID = pointerScreen?.displayUUID

        for screen in NSScreen.screens {
            guard let uuid = screen.displayUUID else { continue }
            let isFullscreen = fullscreenStatusSnapshot[uuid] ?? false
            guard isFullscreen else { continue }

            if pointerUUID == uuid {
                let distanceFromTop = max(0, screen.frame.maxY - mouse.y)

                // NSEvent.mouseLocation is queried directly, so this does not depend
                // on Chrome delivering mouse events or on Accessibility permission.
                if distanceFromTop <= 8 {
                    revealFullscreenNotch(on: uuid)
                    continue
                }

                if fullscreenRevealScreens.contains(uuid) {
                    let viewModel = fullscreenTarget(for: uuid)?.1
                    let keepVisible = distanceFromTop <= 100
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
            } else if fullscreenRevealScreens.contains(uuid) {
                scheduleFullscreenRevealHide(on: uuid)
            }
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
    private func applyFullscreenState() {
        for screen in NSScreen.screens {
            guard let uuid = screen.displayUUID else { continue }
            let isFullscreen = fullscreenBehaviorEnabled
                && (fullscreenStatusSnapshot[uuid] ?? false)

            if isFullscreen {
                if fullscreenRevealScreens.contains(uuid) {
                    revealFullscreenNotch(on: uuid)
                } else {
                    scheduleFullscreenEntryHide(on: uuid)
                }
            } else {
                fullscreenRevealScreens.remove(uuid)
                fullscreenEntryHideWorkItems[uuid]?.cancel()
                fullscreenRevealHideWorkItems[uuid]?.cancel()
                fullscreenCollapseWorkItems[uuid]?.cancel()
                fullscreenEntryHideWorkItems.removeValue(forKey: uuid)
                fullscreenRevealHideWorkItems.removeValue(forKey: uuid)
                fullscreenCollapseWorkItems.removeValue(forKey: uuid)

                if let (notchWindow, viewModel) = fullscreenTarget(for: uuid) {
                    withAnimation(.spring(response: 0.38, dampingFraction: 0.88, blendDuration: 0)) {
                        viewModel.hideOnClosed = false
                    }
                    notchWindow.ignoresMouseEvents = false
                    if !notchWindow.isVisible {
                        notchWindow.orderFrontRegardless()
                    }
                }
            }
        }
    }

'''
app = app[:marker_start] + cleanup_block + methods + app[marker_end:]

old = "        window.alphaValue = 1\n    }\n\n    func applicationDidFinishLaunching"
new = "        window.alphaValue = 1\n        applyFullscreenState()\n    }\n\n    func applicationDidFinishLaunching"
if old not in app:
    raise SystemExit("positionWindow anchor not found")
app = app.replace(old, new, 1)

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
                self.fullscreenStatusSnapshot = fullscreenStatus
                self.fullscreenBehaviorEnabled = enabled
                if !enabled {
                    self.fullscreenRevealScreens.removeAll()
                }
                self.applyFullscreenState()
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

# Disable the stock fullscreen visual observer and let AppDelegate orchestrate
# the delayed collapse/reveal animation. Also make hideOnClosed always shrink
# the software notch to zero regardless of whether the display has a hardware notch.
vm_path = Path("boringNotch/models/BoringViewModel.swift")
vm = vm_path.read_text()

old = "    @Published var hideOnClosed: Bool = true\n\n    @Published var edgeAutoOpenActive: Bool = false\n"
new = "    @Published var hideOnClosed: Bool = false\n    @Published var fullscreenInteractionActive: Bool = false\n\n    @Published var edgeAutoOpenActive: Bool = false\n"
if old not in vm:
    raise SystemExit("view model property anchor not found")
vm = vm.replace(old, new, 1)

old = (
    "            .sink { [weak self] shouldHide in\n"
    "                withAnimation(.smooth) {\n"
    "                    self?.hideOnClosed = shouldHide\n"
    "                }\n"
    "            }\n"
)
new = (
    "            .sink { [weak self] _ in\n"
    "                // AppDelegate owns fullscreen hide/reveal timing so the\n"
    "                // animation is not swallowed by the macOS Space transition.\n"
    "                if self?.hideOnClosed != true {\n"
    "                    self?.hideOnClosed = false\n"
    "                }\n"
    "            }\n"
)
if old not in vm:
    raise SystemExit("view model fullscreen sink anchor not found")
vm = vm.replace(old, new, 1)

old = '''    var effectiveClosedNotchHeight: CGFloat {
        let currentScreen = screenUUID.flatMap { NSScreen.screen(withUUID: $0) }
        let noNotchAndFullscreen = hideOnClosed && (currentScreen?.safeAreaInsets.top ?? 0 <= 0 || currentScreen == nil)
        return noNotchAndFullscreen ? 0 : closedNotchSize.height
    }
'''
new = '''    var effectiveClosedNotchHeight: CGFloat {
        hideOnClosed ? 0 : closedNotchSize.height
    }
'''
if old not in vm:
    raise SystemExit("effectiveClosedNotchHeight anchor not found")
vm = vm.replace(old, new, 1)
vm_path.write_text(vm)

# Keep the interaction latch alive while the user hovers the actual notch, and
# explicitly animate hideOnClosed with the same spring family used by close().
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
    raise SystemExit("ContentView hover anchor not found")
content = content.replace(old, new, 1)

old = '''                            .animation(vm.notchState == .open ? openAnimation : closeAnimation, value: vm.notchState)
                            .animation(.smooth, value: gestureProgress)
'''
new = '''                            .animation(vm.notchState == .open ? openAnimation : closeAnimation, value: vm.notchState)
                            .animation(.spring(response: 0.45, dampingFraction: 1.0, blendDuration: 0), value: vm.hideOnClosed)
                            .animation(.smooth, value: gestureProgress)
'''
if old not in content:
    raise SystemExit("ContentView animation anchor not found")
content = content.replace(old, new, 1)
content_path.write_text(content)

# macOS 26 adds a specific collection behavior for floating/system overlay
# windows that need to join OTHER applications' fullscreen spaces.
window_path = Path("boringNotch/components/Notch/BoringNotchSkyLightWindow.swift")
window = window_path.read_text()
old = '''        collectionBehavior = [
            .fullScreenAuxiliary,
            .stationary,
            .canJoinAllSpaces,
            .ignoresCycle,
        ]
'''
new = '''        var behavior: NSWindow.CollectionBehavior = [
            .fullScreenAuxiliary,
            .stationary,
            .canJoinAllSpaces,
            .ignoresCycle,
        ]
        if #available(macOS 26.0, *) {
            behavior.insert(.canJoinAllApplications)
        }
        collectionBehavior = behavior
'''
if old not in window:
    raise SystemExit("window collectionBehavior anchor not found")
window = window.replace(old, new, 1)
window_path.write_text(window)

# Build-time safety assertions.
assert "canJoinAllApplications" in window
assert "fullscreenPointerTimer" in app
assert "NSEvent.mouseLocation" in app
assert "1.0 / 30.0" in app
assert "orderOut" not in methods
assert "fullscreenInteractionActive" in vm
assert "hideOnClosed ? 0" in vm
assert "value: vm.hideOnClosed" in content

print("v8 patch applied")
print("cross-app fullscreen collection behavior: enabled on macOS 26+")
print("pointer detection: direct NSEvent.mouseLocation watcher at 30 Hz")
print("fullscreen orderOut: none")
print("entry hide delay: 0.55 s to preserve visible native collapse animation")
