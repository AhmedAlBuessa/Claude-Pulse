// Claude Pulse Bar — a tiny native macOS menu-bar host.
//
// macOS 26 (Tahoe) does not reliably render NSStatusItem items created by a
// bare, non-bundled Python process, so the Python `acp-bar` GUI never showed.
// This native, properly-bundled app renders the status item reliably and simply
// calls `acp-bar --print` on a timer to get the usage line to display.

import Cocoa

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?

    private let acpBar = NSHomeDirectory() + "/.local/bin/acp-bar"
    private let acp = NSHomeDirectory() + "/.local/bin/acp"
    private let refreshSeconds: TimeInterval = 60

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // menu-bar only, no Dock icon

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "⚡ …"

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Refresh now", action: #selector(refresh), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Open dashboard", action: #selector(openDashboard), keyEquivalent: "d"))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit Claude Pulse Bar",
                                action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu

        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: refreshSeconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    @objc private func refresh() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self = self else { return }
            let line = self.capture(self.acpBar, ["--print"])
            let text = line.trimmingCharacters(in: .whitespacesAndNewlines)
            DispatchQueue.main.async {
                self.statusItem.button?.title = text.isEmpty ? "⚡ ?%" : text
            }
        }
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
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
