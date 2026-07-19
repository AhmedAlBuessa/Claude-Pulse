// Claude Pulse Bar — a tiny native macOS menu-bar host.
//
// macOS 26 (Tahoe) does not reliably render NSStatusItem items created by a
// bare, non-bundled Python process, so the Python `acp-bar` GUI never showed.
// This native, properly-bundled app renders the status item reliably and calls
// `acp-bar --menu` on a timer for the title text and the dropdown breakdown.

import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private var baseLogo: NSImage?

    private let acpBar = NSHomeDirectory() + "/.local/bin/acp-bar"
    private let acp = NSHomeDirectory() + "/.local/bin/acp"
    private let refreshSeconds: TimeInterval = 60

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // menu-bar only, no Dock icon

        baseLogo = loadLogo()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = baseLogo          // the Claude logo, as-is
            button.imagePosition = .imageLeading
            button.imageHugsTitle = true
            button.title = " …"
        }

        rebuildMenu(details: [])
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: refreshSeconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    // ── data refresh ─────────────────────────────────────────────────────────

    @objc private func refresh() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self = self else { return }
            let out = self.capture(self.acpBar, ["--menu"])
            var lines = out.split(separator: "\n", omittingEmptySubsequences: false)
                .map { String($0).trimmingCharacters(in: .whitespaces) }
            while let last = lines.last, last.isEmpty { lines.removeLast() }

            let title = lines.first ?? ""
            let details = Array(lines.dropFirst()).filter { !$0.isEmpty }
            DispatchQueue.main.async {
                self.statusItem.button?.title = " " + (title.isEmpty ? "?%" : title)
                self.rebuildMenu(details: details)
            }
        }
    }

    private func rebuildMenu(details: [String]) {
        let menu = NSMenu()
        for line in details {
            let item = NSMenuItem(title: line, action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        }
        if !details.isEmpty { menu.addItem(.separator()) }

        let refreshItem = NSMenuItem(title: "Refresh now", action: #selector(refresh), keyEquivalent: "r")
        refreshItem.target = self
        menu.addItem(refreshItem)

        let dashItem = NSMenuItem(title: "Open dashboard", action: #selector(openDashboard), keyEquivalent: "d")
        dashItem.target = self
        menu.addItem(dashItem)

        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Claude Pulse Bar",
                                action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    @objc private func openDashboard() {
        let script = "tell application \"Terminal\"\ndo script \"\(acp)\"\nactivate\nend tell"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        p.arguments = ["-e", script]
        try? p.run()
    }

    private func capture(_ path: String, _ args: [String]) -> String {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: path)
        task.arguments = args
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8) ?? ""
        } catch {
            return ""
        }
    }

    // ── Claude logo, color-coded by usage % ──────────────────────────────────

    private func loadLogo() -> NSImage? {
        var image: NSImage?
        if let url = Bundle.main.url(forResource: "claude-logo", withExtension: "png") {
            image = NSImage(contentsOf: url)
        } else {
            image = NSImage(contentsOfFile: Bundle.main.bundlePath + "/Contents/Resources/claude-logo.png")
        }
        image?.size = NSSize(width: 18, height: 18)
        image?.isTemplate = false  // keep the logo's own (orange) color
        return image
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
