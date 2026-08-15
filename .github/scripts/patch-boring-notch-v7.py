from pathlib import Path

app_path = Path("boringNotch/boringNotchApp.swift")
app = app_path.read_text()

anchor = "@main\nstruct DynamicNotchApp: App {"
trigger_class = '''final class FullscreenTopEdgeTriggerView: NSView {
    var onPointerEntered: (() -> Void)?
    private var edgeTrackingArea: NSTrackingArea?

    override func updateTrackingAreas() {
        if let edgeTrackingArea {
            removeTrackingArea(edgeTrackingArea)
        }

        let tracking = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(tracking)
        edgeTrackingArea = tracking
        super.updateTrackingAreas()
    }

    override func mouseEntered(with event: NSEvent) {
        onPointerEntered?()
    }
}

@main
struct DynamicNotchApp: App {'''
if anchor not in app:
    raise SystemExit("@main anchor not found")
app = app.replace(anchor, trigger_class, 1)

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
    "    private var fullscreenTriggerWindows: [String: NSPanel] = [:]\n"
    "    private var fullscreenRevealHideWorkItems: [String: DispatchWorkItem] = [:]\n"
    "    private var fullscreenHideAnimationWorkItems: [String: DispatchWorkItem] = [:]\n"
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
    "        fullscreenRevealHideWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenHideAnimationWorkItems.values.forEach { $0.cancel() }\n"
    "        fullscreenRevealHideWorkItems.removeAll()\n"
    "        fullscreenHideAnimationWorkItems.removeAll()\n"
    "        fullscreenTriggerWindows.values.forEach { $0.close() }\n"
    "        fullscreenTriggerWindows.removeAll()\n"
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
    raise SystemExit("method anchor not found")
cleanup_block = app[marker_start:marker_end]

methods = '''    @MainActor
    private func notchTarget(for screenUUID: String) -> (NSWindow, BoringViewModel)? {
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
    private func animateFullscreenHide(for screenUUID: String) {
        guard let (notchWindow, viewModel) = notchTarget(for: screenUUID) else { return }

        fullscreenHideAnimationWorkItems[screenUUID]?.cancel()
        notchWindow.ignoresMouseEvents = true

        if viewModel.notchState == .open {
            viewModel.close()

            let item = DispatchWorkItem { [weak self, weak viewModel] in
                Task { @MainActor in
                    guard let self, let viewModel else { return }
                    guard self.fullscreenBehaviorEnabled,
                          (self.fullscreenStatusSnapshot[screenUUID] ?? false),
                          !self.fullscreenRevealScreens.contains(screenUUID)
                    else { return }

                    withAnimation(.smooth(duration: 0.22)) {
                        viewModel.hideOnClosed = true
                    }
                    self.fullscreenHideAnimationWorkItems.removeValue(forKey: screenUUID)
                }
            }
            fullscreenHideAnimationWorkItems[screenUUID] = item
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.30, execute: item)
        } else {
            withAnimation(.smooth(duration: 0.22)) {
                viewModel.hideOnClosed = true
            }
        }
    }

    @MainActor
    private func animateFullscreenReveal(for screenUUID: String) {
        guard let (notchWindow, viewModel) = notchTarget(for: screenUUID) else { return }

        fullscreenHideAnimationWorkItems[screenUUID]?.cancel()
        fullscreenHideAnimationWorkItems.removeValue(forKey: screenUUID)

        withAnimation(.smooth(duration: 0.22)) {
            viewModel.hideOnClosed = false
        }
        notchWindow.ignoresMouseEvents = false
    }

    @MainActor
    private func scheduleFullscreenRevealHide(for screenUUID: String, delay: TimeInterval = 2.8) {
        fullscreenRevealHideWorkItems[screenUUID]?.cancel()

        let item = DispatchWorkItem { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                guard let (_, viewModel) = self.notchTarget(for: screenUUID) else { return }

                if viewModel.fullscreenInteractionActive || viewModel.notchState == .open {
                    self.scheduleFullscreenRevealHide(for: screenUUID, delay: 0.8)
                    return
                }

                self.fullscreenRevealScreens.remove(screenUUID)
                self.fullscreenRevealHideWorkItems.removeValue(forKey: screenUUID)
                self.animateFullscreenHide(for: screenUUID)
            }
        }

        fullscreenRevealHideWorkItems[screenUUID] = item
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
    }

    @MainActor
    private func activateFullscreenReveal(for screenUUID: String) {
        guard fullscreenBehaviorEnabled,
              (fullscreenStatusSnapshot[screenUUID] ?? false)
        else { return }

        fullscreenRevealScreens.insert(screenUUID)
        fullscreenRevealHideWorkItems[screenUUID]?.cancel()
        fullscreenRevealHideWorkItems.removeValue(forKey: screenUUID)

        animateFullscreenReveal(for: screenUUID)
        scheduleFullscreenRevealHide(for: screenUUID)
    }

    @MainActor
    private func refreshFullscreenState() {
        for screen in NSScreen.screens {
            guard let uuid = screen.displayUUID else { continue }
            let isFullscreen = fullscreenBehaviorEnabled
                && (fullscreenStatusSnapshot[uuid] ?? false)

            fullscreenTriggerWindows[uuid]?.ignoresMouseEvents = !isFullscreen

            if !isFullscreen {
                fullscreenRevealScreens.remove(uuid)
                fullscreenRevealHideWorkItems[uuid]?.cancel()
                fullscreenRevealHideWorkItems.removeValue(forKey: uuid)
                fullscreenHideAnimationWorkItems[uuid]?.cancel()
                fullscreenHideAnimationWorkItems.removeValue(forKey: uuid)

                if let (notchWindow, viewModel) = notchTarget(for: uuid) {
                    withAnimation(.smooth(duration: 0.22)) {
                        viewModel.hideOnClosed = false
                    }
                    notchWindow.ignoresMouseEvents = false
                }
            } else if fullscreenRevealScreens.contains(uuid) {
                animateFullscreenReveal(for: uuid)
            } else {
                animateFullscreenHide(for: uuid)
            }
        }
    }

    @MainActor
    private func setupFullscreenTopEdgeTriggers() {
        let currentUUIDs = Set(NSScreen.screens.compactMap { $0.displayUUID })

        for uuid in fullscreenTriggerWindows.keys where !currentUUIDs.contains(uuid) {
            fullscreenTriggerWindows[uuid]?.close()
            fullscreenTriggerWindows.removeValue(forKey: uuid)
        }

        for screen in NSScreen.screens {
            guard let uuid = screen.displayUUID else { continue }
            let height: CGFloat = 3
            let frame = NSRect(
                x: screen.frame.minX,
                y: screen.frame.maxY - height,
                width: screen.frame.width,
                height: height
            )

            let triggerWindow: NSPanel
            if let existing = fullscreenTriggerWindows[uuid] {
                triggerWindow = existing
                triggerWindow.setFrame(frame, display: false)
            } else {
                let panel = NSPanel(
                    contentRect: frame,
                    styleMask: [.borderless, .nonactivatingPanel],
                    backing: .buffered,
                    defer: false,
                    screen: screen
                )
                panel.isOpaque = false
                panel.backgroundColor = .clear
                panel.hasShadow = false
                panel.level = NSWindow.Level(rawValue: NSWindow.Level.mainMenu.rawValue + 4)
                panel.collectionBehavior = [
                    .fullScreenAuxiliary,
                    .stationary,
                    .canJoinAllSpaces,
                    .ignoresCycle,
                ]
                panel.isReleasedWhenClosed = false
                panel.ignoresMouseEvents = true

                let triggerView = FullscreenTopEdgeTriggerView(frame: NSRect(origin: .zero, size: frame.size))
                triggerView.wantsLayer = true
                triggerView.layer?.backgroundColor = NSColor.clear.cgColor
                triggerView.onPointerEntered = { [weak self] in
                    Task { @MainActor in
                        self?.activateFullscreenReveal(for: uuid)
                    }
                }
                panel.contentView = triggerView
                panel.orderFrontRegardless()

                fullscreenTriggerWindows[uuid] = panel
                triggerWindow = panel
            }

            let isFullscreen = fullscreenBehaviorEnabled
                && (fullscreenStatusSnapshot[uuid] ?? false)
            triggerWindow.ignoresMouseEvents = !isFullscreen
            if !triggerWindow.isVisible {
                triggerWindow.orderFrontRegardless()
            }
        }
    }

'''
app = app[:marker_start] + cleanup_block + methods + app[marker_end:]

old = "        window.alphaValue = 1\n    }\n\n    func applicationDidFinishLaunching"
new = "        window.alphaValue = 1\n        refreshFullscreenState()\n    }\n\n    func applicationDidFinishLaunching"
if old not in app:
    raise SystemExit("positionWindow anchor not found")
app = app.replace(old, new, 1)

old = "                self?.adjustWindowPosition(changeAlpha: true)\n                self?.setupDragDetectors()\n"
new = "                self?.adjustWindowPosition(changeAlpha: true)\n                self?.setupFullscreenTopEdgeTriggers()\n                self?.setupDragDetectors()\n"
if old not in app:
    raise SystemExit("selected screen observer anchor not found")
app = app.replace(old, new, 1)

old = "        setupDragDetectors()\n\n        if coordinator.firstLaunch {\n"
if old not in app:
    raise SystemExit("launch anchor not found")
launch = '''        let fullscreenEnabledPublisher = Defaults
            .publisher(.hideNotchOption)
            .map(\\.newValue)
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
                self.setupFullscreenTopEdgeTriggers()
                self.refreshFullscreenState()
            }
        }

        fullscreenStatusSnapshot = FullscreenMediaDetector.shared.fullscreenStatus
        fullscreenBehaviorEnabled = Defaults[.hideNotchOption] != .never
        setupFullscreenTopEdgeTriggers()
        refreshFullscreenState()

        setupDragDetectors()

        if coordinator.firstLaunch {
'''
app = app.replace(old, launch, 1)

old = "                self?.cleanupWindows()\n                self?.adjustWindowPosition()\n                self?.setupDragDetectors()\n"
new = "                self?.cleanupWindows()\n                self?.adjustWindowPosition()\n                self?.setupFullscreenTopEdgeTriggers()\n                self?.setupDragDetectors()\n"
if old not in app:
    raise SystemExit("screen configuration anchor not found")
app = app.replace(old, new, 1)

app_path.write_text(app)

vm_path = Path("boringNotch/models/BoringViewModel.swift")
vm = vm_path.read_text()

old = "    @Published var hideOnClosed: Bool = true\n"
new = "    @Published var hideOnClosed: Bool = true\n    @Published var fullscreenInteractionActive: Bool = false\n"
if old not in vm:
    raise SystemExit("hideOnClosed property anchor not found")
vm = vm.replace(old, new, 1)

old = '''            .sink { [weak self] shouldHide in
                withAnimation(.smooth) {
                    self?.hideOnClosed = shouldHide
                }
            }
'''
new = '''            .sink { _ in
                // Fullscreen visibility is managed by AppDelegate in this custom build.
            }
'''
if old not in vm:
    raise SystemExit("fullscreen observer sink anchor not found")
vm = vm.replace(old, new, 1)

old = '''    var effectiveClosedNotchHeight: CGFloat {
        let currentScreen = screenUUID.flatMap { NSScreen.screen(withUUID: $0) }
        let noNotchAndFullscreen = hideOnClosed && (currentScreen?.safeAreaInsets.top ?? 0 <= 0 || currentScreen == nil)
        return noNotchAndFullscreen ? 0 : closedNotchSize.height
    }
'''
new = '''    var effectiveClosedNotchHeight: CGFloat {
        return hideOnClosed ? 0 : closedNotchSize.height
    }
'''
if old not in vm:
    raise SystemExit("effectiveClosedNotchHeight anchor not found")
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
    raise SystemExit("ContentView onHover anchor not found")
content = content.replace(old, new, 1)
content_path.write_text(content)

assert "FullscreenTopEdgeTriggerView" in app
assert ".activeAlways" in app
assert "fullscreenTriggerWindows" in app
assert "addGlobalMonitorForEvents" not in app
assert "viewModel.close()" in app
assert "withAnimation(.smooth(duration: 0.22))" in app
assert "notchWindow.alphaValue = 0" not in app
assert "fullscreenInteractionActive" in vm
assert "return hideOnClosed ? 0 : closedNotchSize.height" in vm
assert "vm.fullscreenInteractionActive = hovering" in content

print("v7 top-edge trigger applied")
print("top edge AppKit tracking strip: yes")
print("global mouse monitoring: no")
print("native close spring preserved: yes")
print("closed-notch smooth shrink to zero: yes")
print("main notch orderOut/alpha hide: no")
