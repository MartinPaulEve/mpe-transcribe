/*
 * transcribe_launcher.c — Native Mach-O trampoline for Transcribe.app
 *
 * macOS TCC (Transparency, Consent, and Control) requires that bundled
 * apps use a native Mach-O main executable.  Shell scripts and Python
 * interpreters do not get stable TCC identity.
 *
 * This launcher monitors the global hotkey via CGEventTap (which gets
 * accessibility permissions from the .app bundle's TCC grant) and
 * signals the Python child with SIGUSR1 when the hotkey is pressed.
 * This avoids the problem of pynput in the Python child not having
 * accessibility — the C launcher IS the TCC-tracked process.
 *
 * The Python path and PYTHONPATH are baked in at compile time by the
 * install script via -D flags.
 */

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

/* These are set by the install script at compile time:
 *   -DPYTHON_BIN="/path/to/python3"
 *   -DPYTHON_PATH="/path/to/src"
 *   -DHOTKEY_KEYCODE=0x27       (kVK_ANSI_Quote for ')
 *   -DHOTKEY_MODIFIERS=0x120000 (Cmd+Shift)
 */
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

/* Stringify macros */
#define _STR(x) #x
#define STR(x) _STR(x)

/* Mask to isolate modifier keys we care about (ignore CapsLock, etc.) */
#define MODIFIER_MASK \
    (kCGEventFlagMaskCommand | kCGEventFlagMaskShift | \
     kCGEventFlagMaskAlternate | kCGEventFlagMaskControl)

#define DEBOUNCE_SECONDS 0.3

static pid_t child_pid = 0;
static CFRunLoopRef main_loop = NULL;
static CFMachPortRef event_tap = NULL;
static double last_press = 0.0;

static double monotonic_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static CGEventRef hotkey_callback(
    CGEventTapProxy proxy,
    CGEventType type,
    CGEventRef event,
    void *info
) {
    /* Re-enable if macOS disables the tap (e.g. timeout). */
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

static void forward_signal(int sig) {
    if (child_pid > 0) {
        kill(child_pid, sig);
    }
    if (main_loop) {
        CFRunLoopStop(main_loop);
    }
}

static void on_sigchld(int sig) {
    if (main_loop) {
        CFRunLoopStop(main_loop);
    }
}

int main(int argc, char *argv[]) {
    /* Set PYTHONPATH so the transcribe package is importable. */
    const char *existing = getenv("PYTHONPATH");
    if (existing && existing[0]) {
        char *combined;
        if (asprintf(&combined, "%s:%s", STR(PYTHON_PATH), existing) > 0) {
            setenv("PYTHONPATH", combined, 1);
            free(combined);
        }
    } else {
        setenv("PYTHONPATH", STR(PYTHON_PATH), 1);
    }

    /* Tell the Python child that hotkeys are handled by the launcher. */
    setenv("TRANSCRIBE_LAUNCHER", "1", 1);

    child_pid = fork();
    if (child_pid < 0) {
        perror("fork");
        return 1;
    }

    if (child_pid == 0) {
        /* Child: exec Python -m transcribe */
        execl(STR(PYTHON_BIN), "python", "-m", "transcribe", NULL);
        /* If exec fails: */
        perror("execl");
        _exit(1);
    }

    /* Parent: set up signal handlers. */
    signal(SIGTERM, forward_signal);
    signal(SIGINT, forward_signal);
    signal(SIGHUP, forward_signal);
    signal(SIGCHLD, on_sigchld);

    /* Set up CGEventTap to monitor the hotkey.
     * This requires accessibility permissions for the .app bundle. */
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
            "transcribe-launcher: could not create event tap — "
            "grant Accessibility to Transcribe.app in "
            "System Settings → Privacy & Security → Accessibility\n");
    }

    /* Wait for child to exit. */
    int status;
    while (waitpid(child_pid, &status, 0) < 0) {
        if (errno != EINTR)
            break;
    }

    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return 1;
}
