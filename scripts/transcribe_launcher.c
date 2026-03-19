/*
 * transcribe_launcher.c — Native Mach-O launcher for Transcribe.app
 *
 * macOS TCC requires a native Mach-O main executable inside a signed
 * .app bundle for stable accessibility and microphone grants.
 *
 * This launcher:
 *  1. Initialises NSApplication so macOS recognises the process as a
 *     proper app (required for TCC to associate it with the .app bundle)
 *  2. Forks and exec's the Python transcribe process as a child
 *  3. Registers a global hotkey via RegisterEventHotKey (Carbon).
 *     This consumes the keystroke so it never reaches the focused app,
 *     and does NOT require accessibility permissions.
 *  4. If RegisterEventHotKey fails, falls back to a listen-only
 *     CGEventTap (requires accessibility, keystroke passes through).
 *  5. Sends SIGUSR1 to the Python child when the hotkey is pressed
 *  6. Forwards SIGTERM/SIGINT/SIGHUP to the child for clean shutdown
 */

#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <Carbon/Carbon.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <objc/message.h>
#include <objc/runtime.h>

/* Compile-time configuration from the install script. */
#ifndef PYTHON_BIN
#error "PYTHON_BIN must be defined at compile time"
#endif
#ifndef PYTHON_PATH
#error "PYTHON_PATH must be defined at compile time"
#endif
#ifndef HOTKEY_KEYCODE
#define HOTKEY_KEYCODE 0x27  /* kVK_ANSI_Quote (') */
#endif
#ifndef HOTKEY_MODIFIERS
#define HOTKEY_MODIFIERS 0x120000  /* Cmd+Shift (CGEvent flags) */
#endif

#define _STR(x) #x
#define STR(x) _STR(x)

/* Mask to isolate the modifier keys we care about (for CGEventTap fallback). */
#define MODIFIER_MASK \
    (kCGEventFlagMaskCommand | kCGEventFlagMaskShift | \
     kCGEventFlagMaskAlternate | kCGEventFlagMaskControl)

#define DEBOUNCE_SECONDS 0.3

static pid_t child_pid = 0;
static CFRunLoopRef main_loop = NULL;
static CFMachPortRef event_tap = NULL;
static double last_press = 0.0;

/* ── Helpers ────────────────────────────────────────────────────── */

static double monotonic_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void send_hotkey_signal(void) {
    double now = monotonic_seconds();
    if (now - last_press >= DEBOUNCE_SECONDS) {
        last_press = now;
        if (child_pid > 0)
            kill(child_pid, SIGUSR1);
    }
}

/*
 * Convert CGEvent modifier flags to Carbon modifier flags.
 *
 * CGEvent:  kCGEventFlagMaskCommand  = 0x100000
 *           kCGEventFlagMaskShift    = 0x020000
 *           kCGEventFlagMaskAlternate= 0x080000
 *           kCGEventFlagMaskControl  = 0x040000
 *
 * Carbon:   cmdKey     = 0x0100
 *           shiftKey   = 0x0200
 *           optionKey  = 0x0800
 *           controlKey = 0x1000
 */
static UInt32 cg_to_carbon_modifiers(CGEventFlags cg) {
    UInt32 carbon = 0;
    if (cg & kCGEventFlagMaskCommand)   carbon |= cmdKey;
    if (cg & kCGEventFlagMaskShift)     carbon |= shiftKey;
    if (cg & kCGEventFlagMaskAlternate) carbon |= optionKey;
    if (cg & kCGEventFlagMaskControl)   carbon |= controlKey;
    return carbon;
}

/*
 * Initialise NSApplication so the window server and TCC recognise
 * this process as a bundled macOS app.  Without this, a binary
 * launched directly by launchd is treated as a generic command-line
 * tool and TCC won't match it to the .app's accessibility grant.
 */
static void init_nsapp(void) {
    dlopen(
        "/System/Library/Frameworks/AppKit.framework/AppKit",
        RTLD_LAZY);

    Class cls = (Class)objc_getClass("NSApplication");
    if (!cls) {
        fprintf(stderr, "transcribe-launcher: "
            "could not load NSApplication\n");
        return;
    }

    SEL shared_sel = sel_registerName("sharedApplication");
    id app = ((id (*)(Class, SEL))objc_msgSend)(cls, shared_sel);
    if (!app) return;

    /* NSApplicationActivationPolicyAccessory = 1 */
    SEL policy_sel = sel_registerName("setActivationPolicy:");
    ((void (*)(id, SEL, long))objc_msgSend)(app, policy_sel, 1);
}

static void log_diagnostics(void) {
    CFBundleRef bundle = CFBundleGetMainBundle();
    if (bundle) {
        CFStringRef bid = CFBundleGetIdentifier(bundle);
        if (bid) {
            char buf[256];
            CFStringGetCString(
                bid, buf, sizeof(buf), kCFStringEncodingUTF8);
            fprintf(stderr,
                "transcribe-launcher: bundle ID = %s\n", buf);
        } else {
            fprintf(stderr,
                "transcribe-launcher: bundle has no identifier\n");
        }
    } else {
        fprintf(stderr,
            "transcribe-launcher: WARNING — no main bundle found\n");
    }
}

/* ── RegisterEventHotKey (primary — consumes keystroke) ─────────── */

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

static OSStatus carbon_hotkey_handler(
    EventHandlerCallRef next_handler,
    EventRef event,
    void *user_data
) {
    (void)next_handler;
    (void)event;
    (void)user_data;
    send_hotkey_signal();
    return noErr;
}

/*
 * Register a global hotkey via the Carbon Event Manager.
 * This consumes the keystroke (it never reaches the focused app)
 * and does NOT require accessibility permissions.
 * Returns true on success.
 */
static bool register_carbon_hotkey(void) {
    EventTypeSpec event_type = {
        kEventClassKeyboard, kEventHotKeyPressed
    };

    OSStatus err = InstallApplicationEventHandler(
        &carbon_hotkey_handler, 1, &event_type, NULL, NULL);
    if (err != noErr) {
        fprintf(stderr,
            "transcribe-launcher: InstallApplicationEventHandler "
            "failed (%d)\n", (int)err);
        return false;
    }

    UInt32 carbon_mods = cg_to_carbon_modifiers(
        (CGEventFlags)HOTKEY_MODIFIERS);

    EventHotKeyID hotkey_id = { 'TRNS', 1 };
    EventHotKeyRef hotkey_ref = NULL;

    err = RegisterEventHotKey(
        HOTKEY_KEYCODE,
        carbon_mods,
        hotkey_id,
        GetApplicationEventTarget(),
        0,
        &hotkey_ref
    );

    if (err != noErr) {
        fprintf(stderr,
            "transcribe-launcher: RegisterEventHotKey failed (%d)\n",
            (int)err);
        return false;
    }

    fprintf(stderr,
        "transcribe-launcher: hotkey registered via Carbon "
        "(keycode=0x%02x carbon_modifiers=0x%04x) — "
        "keystroke will be consumed\n",
        HOTKEY_KEYCODE, carbon_mods);
    return true;
}

#pragma clang diagnostic pop

/* ── CGEventTap fallback (listen-only, needs accessibility) ─────── */

static CGEventRef eventtap_callback(
    CGEventTapProxy proxy,
    CGEventType type,
    CGEventRef event,
    void *info
) {
    if (type == kCGEventTapDisabledByTimeout ||
        type == kCGEventTapDisabledByUserInput) {
        if (event_tap)
            CGEventTapEnable(event_tap, true);
        return event;
    }

    if (type != kCGEventKeyDown)
        return event;

    CGKeyCode keycode = (CGKeyCode)CGEventGetIntegerValueField(
        event, kCGKeyboardEventKeycode);
    CGEventFlags flags = CGEventGetFlags(event) & MODIFIER_MASK;

    if (keycode == HOTKEY_KEYCODE &&
        flags == (CGEventFlags)HOTKEY_MODIFIERS) {
        send_hotkey_signal();
    }

    /* Listen-only tap — always pass the event through. */
    return event;
}

/*
 * Set up a listen-only CGEventTap as a fallback.
 * Returns true on success.
 */
static bool setup_eventtap_fallback(void) {
    CGEventMask mask = (1 << kCGEventKeyDown);
    event_tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        eventtap_callback,
        NULL
    );

    if (!event_tap)
        return false;

    CFRunLoopSourceRef source =
        CFMachPortCreateRunLoopSource(NULL, event_tap, 0);
    main_loop = CFRunLoopGetCurrent();
    CFRunLoopAddSource(main_loop, source, kCFRunLoopCommonModes);
    CGEventTapEnable(event_tap, true);
    CFRelease(source);

    fprintf(stderr,
        "transcribe-launcher: hotkey monitor active via CGEventTap "
        "(listen-only, keycode=0x%02x modifiers=0x%06x)\n"
        "  Note: keystroke will pass through to focused app\n",
        HOTKEY_KEYCODE, HOTKEY_MODIFIERS);
    return true;
}

/* ── Signal handlers ────────────────────────────────────────────── */

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

static void forward_signal(int sig) {
    if (child_pid > 0)
        kill(child_pid, sig);
    QuitApplicationEventLoop();
}

static void on_sigchld(int sig) {
    QuitApplicationEventLoop();
}

#pragma clang diagnostic pop

/* ── Main ───────────────────────────────────────────────────────── */

int main(int argc, char *argv[]) {
    init_nsapp();
    log_diagnostics();

    /* Set PYTHONPATH so the transcribe package is importable. */
    const char *existing = getenv("PYTHONPATH");
    if (existing && existing[0]) {
        char *combined;
        if (asprintf(&combined, "%s:%s",
                     STR(PYTHON_PATH), existing) > 0) {
            setenv("PYTHONPATH", combined, 1);
            free(combined);
        }
    } else {
        setenv("PYTHONPATH", STR(PYTHON_PATH), 1);
    }

    setenv("TRANSCRIBE_LAUNCHER", "1", 1);

    child_pid = fork();
    if (child_pid < 0) {
        perror("fork");
        return 1;
    }

    if (child_pid == 0) {
        execl(STR(PYTHON_BIN), "python", "-m", "transcribe", NULL);
        perror("execl");
        _exit(1);
    }

    /* Parent: set up signal handlers. */
    signal(SIGTERM, forward_signal);
    signal(SIGINT, forward_signal);
    signal(SIGHUP, forward_signal);
    signal(SIGCHLD, on_sigchld);

    /*
     * Try RegisterEventHotKey first (consumes keystroke, no
     * accessibility needed).  Fall back to listen-only CGEventTap
     * if that fails (needs accessibility, keystroke passes through).
     */
    bool hotkey_ok = register_carbon_hotkey();

    if (!hotkey_ok) {
        fprintf(stderr,
            "transcribe-launcher: Carbon hotkey failed, "
            "trying CGEventTap fallback...\n");
        hotkey_ok = setup_eventtap_fallback();
    }

    if (!hotkey_ok) {
        fprintf(stderr,
            "transcribe-launcher: could not register hotkey\n"
            "  Grant Accessibility to Transcribe.app:\n"
            "  System Settings → Privacy & Security → Accessibility\n"
            "  Then restart: launchctl stop com.mpe.transcribe && "
            "launchctl start com.mpe.transcribe\n");
    }

    /* RunApplicationEventLoop dispatches Carbon hotkey events
     * (which CFRunLoopRun alone does NOT).  It also dispatches
     * CGEventTap callbacks since both use the main run loop. */
    main_loop = CFRunLoopGetCurrent();

    #pragma clang diagnostic push
    #pragma clang diagnostic ignored "-Wdeprecated-declarations"
    RunApplicationEventLoop();
    #pragma clang diagnostic pop

    /* Cleanup. */
    if (event_tap) {
        CGEventTapEnable(event_tap, false);
        CFRelease(event_tap);
        event_tap = NULL;
    }

    int status;
    while (waitpid(child_pid, &status, 0) < 0) {
        if (errno != EINTR)
            break;
    }

    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return 1;
}
