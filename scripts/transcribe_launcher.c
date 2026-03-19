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
 *  3. Monitors the global hotkey via CGEventTap (which uses the .app's
 *     TCC accessibility grant — the Python child doesn't need it)
 *  4. Sends SIGUSR1 to the Python child when the hotkey is pressed
 *  5. Forwards SIGTERM/SIGINT/SIGHUP to the child for clean shutdown
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
#define HOTKEY_MODIFIERS 0x120000  /* Cmd+Shift */
#endif

#define _STR(x) #x
#define STR(x) _STR(x)

/* Mask to isolate the modifier keys we care about. */
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

/*
 * Initialise NSApplication so the window server and TCC recognise
 * this process as a bundled macOS app.  Without this, a binary
 * launched directly by launchd is treated as a generic command-line
 * tool and TCC won't match it to the .app's accessibility grant.
 */
static void init_nsapp(void) {
    /* Load AppKit (pulls in Foundation etc.) */
    dlopen(
        "/System/Library/Frameworks/AppKit.framework/AppKit",
        RTLD_LAZY);

    Class cls = (Class)objc_getClass("NSApplication");
    if (!cls) {
        fprintf(stderr, "transcribe-launcher: "
            "could not load NSApplication\n");
        return;
    }

    /* [NSApplication sharedApplication] — creates the singleton. */
    SEL shared_sel = sel_registerName("sharedApplication");
    id app = ((id (*)(Class, SEL))objc_msgSend)(cls, shared_sel);
    if (!app) return;

    /*
     * setActivationPolicy:  NSApplicationActivationPolicyAccessory = 1
     * This marks the process as a background agent — no Dock icon,
     * no menu bar, but it IS a proper app for TCC purposes.
     */
    SEL policy_sel = sel_registerName("setActivationPolicy:");
    ((void (*)(id, SEL, long))objc_msgSend)(app, policy_sel, 1);
}

/*
 * Log the bundle identity and TCC status for diagnostics.
 */
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

/* ── CGEventTap hotkey callback ─────────────────────────────────── */

static CGEventRef hotkey_callback(
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
        double now = monotonic_seconds();
        if (now - last_press >= DEBOUNCE_SECONDS) {
            last_press = now;
            if (child_pid > 0) {
                kill(child_pid, SIGUSR1);
            }
        }
    }

    return event;
}

/* ── Signal handlers ────────────────────────────────────────────── */

static void forward_signal(int sig) {
    if (child_pid > 0)
        kill(child_pid, sig);
    if (main_loop)
        CFRunLoopStop(main_loop);
}

static void on_sigchld(int sig) {
    if (main_loop)
        CFRunLoopStop(main_loop);
}

/* ── Main ───────────────────────────────────────────────────────── */

int main(int argc, char *argv[]) {
    /*
     * Register as a proper macOS app BEFORE doing anything else.
     * This must happen before CGEventTapCreate so that TCC can
     * look up the .app bundle's accessibility grant.
     */
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

    /* Tell the Python child that hotkeys are handled by us. */
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

    /* Create CGEventTap for the hotkey.  This needs the .app's
     * accessibility TCC grant — init_nsapp() above ensures TCC
     * can identify us as the app. */
    CGEventMask mask = (1 << kCGEventKeyDown);
    event_tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        hotkey_callback,
        NULL
    );

    if (event_tap) {
        CFRunLoopSourceRef source =
            CFMachPortCreateRunLoopSource(NULL, event_tap, 0);
        main_loop = CFRunLoopGetCurrent();
        CFRunLoopAddSource(main_loop, source, kCFRunLoopCommonModes);
        CGEventTapEnable(event_tap, true);

        fprintf(stderr,
            "transcribe-launcher: hotkey monitor active "
            "(keycode=0x%02x modifiers=0x%06x)\n",
            HOTKEY_KEYCODE, HOTKEY_MODIFIERS);

        CFRunLoopRun();

        CGEventTapEnable(event_tap, false);
        CFRelease(source);
        CFRelease(event_tap);
        event_tap = NULL;
    } else {
        fprintf(stderr,
            "transcribe-launcher: could not create event tap\n"
            "  Grant Accessibility to Transcribe.app:\n"
            "  System Settings → Privacy & Security → Accessibility\n"
            "  Then restart: launchctl stop com.mpe.transcribe && "
            "launchctl start com.mpe.transcribe\n");
    }

    /* Wait for child to exit. */
    int status;
    while (waitpid(child_pid, &status, 0) < 0) {
        if (errno != EINTR)
            break;
    }

    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return 1;
}
