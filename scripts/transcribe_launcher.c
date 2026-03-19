/*
 * transcribe_launcher.c — Native Mach-O trampoline for Transcribe.app
 *
 * macOS TCC (Transparency, Consent, and Control) requires that bundled
 * apps use a native Mach-O main executable.  Shell scripts and Python
 * interpreters do not get stable TCC identity.  This tiny C program
 * serves as the CFBundleExecutable: it launches Python as a child
 * process and forwards signals for clean shutdown.
 *
 * The Python path and PYTHONPATH are baked in at compile time by the
 * install script via -D flags.
 */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

/* These are set by the install script at compile time:
 *   -DPYTHON_BIN="/path/to/python3"
 *   -DPYTHON_PATH="/path/to/src"
 */
#ifndef PYTHON_BIN
#error "PYTHON_BIN must be defined at compile time"
#endif
#ifndef PYTHON_PATH
#error "PYTHON_PATH must be defined at compile time"
#endif

/* Stringify macros */
#define _STR(x) #x
#define STR(x) _STR(x)

static pid_t child_pid = 0;

static void forward_signal(int sig) {
    if (child_pid > 0) {
        kill(child_pid, sig);
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

    /* Parent: forward termination signals to the child. */
    signal(SIGTERM, forward_signal);
    signal(SIGINT, forward_signal);
    signal(SIGHUP, forward_signal);

    /* Wait for the child to exit. */
    int status;
    waitpid(child_pid, &status, 0);

    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return 1;
}
