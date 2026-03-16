// Wispr Transcription - Windows keyboard hook
// Compiled during install, launched via PowerShell Start-Process from the WSL daemon.
// Installs a WH_KEYBOARD_LL hook and sends KEY_DOWN/KEY_UP events over TCP.
// Also shows a native Windows recording overlay and handles paste via keybd_event.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Windows.Forms;

class WisprKeyHook {
    const int WH_KEYBOARD_LL = 13;
    const int WM_KEYDOWN = 0x0100;
    const int WM_KEYUP = 0x0101;
    const int WM_SYSKEYDOWN = 0x0104;
    const int WM_SYSKEYUP = 0x0105;

    delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    struct KBDLLHOOKSTRUCT {
        public int vkCode;
        public int scanCode;
        public int flags;
        public int time;
        public IntPtr dwExtraInfo;
    }

    [DllImport("user32.dll", SetLastError = true)]
    static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn,
        IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll")]
    static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll")]
    static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode,
        IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll")]
    static extern IntPtr GetModuleHandle(string lpModuleName);

    [DllImport("kernel32.dll")]
    static extern uint GetLastError();

    // keybd_event injects keystrokes globally from a process with a LL keyboard hook.
    // More reliable than SendKeys for apps like Windows Terminal.
    [DllImport("user32.dll")]
    static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    static StreamWriter _writer;
    static StreamWriter _log;
    static IntPtr _hookID = IntPtr.Zero;
    static LowLevelKeyboardProc _proc;
    static int _targetVK;
    static bool _keyDown = false;
    static int _callbackCount = 0;
    static Form _overlay;

    static void Log(string msg) {
        try { _log.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " " + msg); _log.Flush(); } catch {}
    }

    static IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam) {
        _callbackCount++;
        if (nCode >= 0) {
            var kbs = Marshal.PtrToStructure<KBDLLHOOKSTRUCT>(lParam);
            int msg = wParam.ToInt32();
            if (_callbackCount <= 5 || kbs.vkCode == _targetVK) {
                Log("CB: vk=0x" + kbs.vkCode.ToString("X2") + " msg=0x" + msg.ToString("X4")
                    + " total=" + _callbackCount);
            }
            if (kbs.vkCode == _targetVK) {
                if ((msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN) && !_keyDown) {
                    _keyDown = true;
                    try { _writer.WriteLine("KEY_DOWN"); _writer.Flush(); } catch {}
                } else if ((msg == WM_KEYUP || msg == WM_SYSKEYUP) && _keyDown) {
                    _keyDown = false;
                    try { _writer.WriteLine("KEY_UP"); _writer.Flush(); } catch {}
                }
            }
        }
        return CallNextHookEx(_hookID, nCode, wParam, lParam);
    }

    // Show a small red "● REC" overlay in the top-right corner of the primary screen.
    static Form CreateOverlay() {
        var form = new Form {
            FormBorderStyle = FormBorderStyle.None,
            ShowInTaskbar = false,
            TopMost = true,
            StartPosition = FormStartPosition.Manual,
            Width = 90,
            Height = 32,
            Opacity = 0.92,
            BackColor = Color.FromArgb(220, 38, 38),
        };
        var label = new Label {
            Text = "\u25cf REC",
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 10, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleCenter,
            Dock = DockStyle.Fill,
        };
        form.Controls.Add(label);
        var area = Screen.PrimaryScreen.WorkingArea;
        form.Location = new Point(area.Right - form.Width - 20, area.Top + 20);
        return form;
    }

    // Inject Ctrl+V keystrokes globally. Works from a process that has a LL keyboard hook.
    static void SendCtrlV() {
        const uint KEYUP = 2;
        keybd_event(0x11, 0, 0, UIntPtr.Zero);      // VK_CONTROL down
        keybd_event(0x56, 0, 0, UIntPtr.Zero);      // V down
        keybd_event(0x56, 0, KEYUP, UIntPtr.Zero);  // V up
        keybd_event(0x11, 0, KEYUP, UIntPtr.Zero);  // VK_CONTROL up
        Log("Sent Ctrl+V");
    }

    static void Cleanup() {
        if (_hookID != IntPtr.Zero) {
            UnhookWindowsHookEx(_hookID);
            _hookID = IntPtr.Zero;
        }
        if (_overlay != null) {
            try { _overlay.Close(); } catch {}
            _overlay = null;
        }
    }

    [STAThread]
    static void Main(string[] args) {
        // Open log file next to the exe
        string logPath = Path.Combine(Path.GetTempPath(), "wispr_keyhook.log");
        _log = new StreamWriter(logPath, false) { AutoFlush = true };
        Log("Starting. Args: " + string.Join(" ", args));
        Log("PID: " + Process.GetCurrentProcess().Id);
        Log("Session: " + Process.GetCurrentProcess().SessionId);

        if (args.Length < 3) {
            Log("ERROR: Usage: keyhook.exe <host> <port> <vkcode>");
            _log.Close();
            return;
        }
        string host = args[0];
        int port = int.Parse(args[1]);
        _targetVK = int.Parse(args[2]);
        Log("Host: " + host + ", Port: " + port + ", TargetVK: 0x" + _targetVK.ToString("X2"));

        // Connect to the WSL daemon over TCP
        TcpClient client;
        try {
            client = new TcpClient(host, port);
            Log("TCP connected");
        } catch (Exception e) {
            Log("TCP connect failed: " + e.Message);
            _log.Close();
            return;
        }
        var stream = client.GetStream();
        _writer = new StreamWriter(stream) { AutoFlush = true };
        var reader = new StreamReader(stream);

        // Install keyboard hook
        _proc = new LowLevelKeyboardProc(HookCallback);
        IntPtr hMod = GetModuleHandle(null);
        Log("Module handle: 0x" + hMod.ToString("X"));
        _hookID = SetWindowsHookEx(WH_KEYBOARD_LL, _proc, hMod, 0);
        uint hookErr = GetLastError();
        Log("Hook handle: 0x" + _hookID.ToString("X") + ", LastError: " + hookErr);

        if (_hookID == IntPtr.Zero) {
            Log("HOOK FAILED");
            _writer.WriteLine("HOOK_FAILED");
            client.Close();
            _log.Close();
            return;
        }
        _writer.WriteLine("HOOK_READY");
        Log("HOOK_READY sent, entering message loop");

        // Poll for commands from daemon (RECORD_START, RECORD_STOP, PASTE, QUIT).
        // 100ms interval keeps paste latency low without hammering the CPU.
        var checkTimer = new Timer { Interval = 100 };
        int timerTicks = 0;
        checkTimer.Tick += (s, e) => {
            timerTicks++;
            if (timerTicks <= 3 || timerTicks % 100 == 0) {
                Log("Timer tick " + timerTicks + ", callbacks=" + _callbackCount);
            }
            try {
                // Drain all pending commands before checking connection state
                while (stream.DataAvailable) {
                    string line = reader.ReadLine();
                    if (line == null) {
                        Log("TCP disconnected, exiting");
                        Cleanup();
                        Application.ExitThread();
                        return;
                    }
                    string cmd = line.Trim();
                    Log("CMD: " + cmd);
                    if (cmd == "QUIT") {
                        Log("QUIT received, exiting");
                        Cleanup();
                        Application.ExitThread();
                        return;
                    } else if (cmd == "RECORD_START") {
                        if (_overlay == null) {
                            _overlay = CreateOverlay();
                            _overlay.Show();
                        }
                    } else if (cmd == "RECORD_STOP") {
                        if (_overlay != null) {
                            _overlay.Close();
                            _overlay = null;
                        }
                    } else if (cmd == "PASTE") {
                        SendCtrlV();
                    }
                }
                if (!client.Connected) {
                    Log("TCP disconnected, exiting");
                    Cleanup();
                    Application.ExitThread();
                }
            } catch (Exception ex) {
                Log("Timer exception: " + ex.Message);
                Cleanup();
                Application.ExitThread();
            }
        };
        checkTimer.Start();

        // Pump messages (required for WH_KEYBOARD_LL callbacks and WinForms)
        Application.Run();

        Log("Application.Run() returned, total callbacks=" + _callbackCount);
        try { _writer.Close(); } catch {}
        try { client.Close(); } catch {}
        _log.Close();
    }
}
