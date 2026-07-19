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
            button.image = tintedLogo(color: colorForPct(nil))  // neutral until first refresh
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
            let pct = self.parsePct(title)
            DispatchQueue.main.async {
                self.statusItem.button?.image = self.tintedLogo(color: self.colorForPct(pct))
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
        if let url = Bundle.main.url(forResource: "claude-logo", withExtension: "png") {
            return NSImage(contentsOf: url)
        }
        // Fallback: next to the executable's bundle Resources.
        let path = Bundle.main.bundlePath + "/Contents/Resources/claude-logo.png"
        return NSImage(contentsOfFile: path)
    }

    /// Green (low) → yellow → orange → red (high). Gray when unknown.
    private func colorForPct(_ pct: Int?) -> NSColor {
        guard let p = pct else { return .systemGray }
        switch p {
        case 90...:    return .systemRed
        case 70..<90:  return .systemOrange
        case 40..<70:  return .systemYellow
        default:       return .systemGreen
        }
    }

    /// Recolor the logo silhouette to `color` (keeps the spark shape, drops the orange).
    private func tintedLogo(color: NSColor, size: CGFloat = 15) -> NSImage? {
        guard let base = baseLogo else { return nil }
        let out = NSImage(size: NSSize(width: size, height: size))
        out.lockFocus()
        let rect = NSRect(x: 0, y: 0, width: size, height: size)
        base.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1.0)
        color.set()
        rect.fill(using: .sourceAtop)   // paint color only where the logo is opaque
        out.unlockFocus()
        out.isTemplate = false          // use our own color, not the system tint
        return out
    }

    /// Pull the integer percentage out of a title like "██░░ 48%".
    private func parsePct(_ text: String) -> Int? {
        guard let r = text.range(of: #"\d+%"#, options: .regularExpression) else { return nil }
        return Int(text[r].dropLast())
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
