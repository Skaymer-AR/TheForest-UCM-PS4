// The Forest CUSA12398 1.15 -- v0.8 safety hold (NO HOOKS; no GUI).
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "plugin_common.h"
#include "ps4_backend.h"

static int loaded;

attr_public const char *g_pluginName = "theforest_ucm_diag";
attr_public const char *g_pluginDesc =
    "The Forest safe no-hook baseline after v0.6 PS4 lockup";
attr_public const char *g_pluginAuth = "The Forest UCM PS4 research";
attr_public uint32_t g_pluginVersion = 0x00000800;

static int is_expected_version(const char *version) {
    if (!version) return 0;
    return strcmp(version, "01.15") == 0 || strcmp(version, "1.15") == 0;
}

static void log_safe_status(const char *event,
                            const Ps4BackendStatus *status) {
    final_printf(
        "[TF-UCM] %s profile=%s hooks=OFF renderer=OFF framebuffer=OFF "
        "controller=OFF gameplay_writes=OFF\n",
        event, status->profile);
}

int32_t attr_public plugin_load(int32_t argc, const char *argv[]) {
    struct proc_info procInfo;
    Ps4BackendStatus status;
    (void)argc;
    (void)argv;

    if (loaded) return -1;
    if (sys_sdk_proc_info(&procInfo) != 0) {
        final_printf("[TF-UCM-DIAG] proc_info unavailable; load refused.\n");
        return -1;
    }
    if (!memchr(procInfo.titleid, 0, sizeof(procInfo.titleid)) ||
        !memchr(procInfo.version, 0, sizeof(procInfo.version))) return -1;
    if (strcmp(procInfo.titleid, "CUSA12398") != 0 ||
        !is_expected_version(procInfo.version)) {
        final_printf("[TF-UCM-DIAG] target mismatch: title=%s, version=%s\n",
                     procInfo.titleid, procInfo.version);
        return -1;
    }

    if (!ps4_backend_start()) {
        ps4_backend_get_status(&status);
        log_safe_status("no-hook startup refused", &status);
        return -1;
    }

    loaded = 1;
    ps4_backend_get_status(&status);
    log_safe_status("loaded", &status);
    NotifyStatic(TEX_ICON_SYSTEM,
                 "The Forest UCM safe baseline (NO HOOKS / NO MENU)");
    return 0;
}

int32_t attr_public plugin_unload(int32_t argc, const char *argv[]) {
    Ps4BackendStatus status;
    (void)argc;
    (void)argv;

    ps4_backend_stop();
    ps4_backend_get_status(&status);
    log_safe_status("unloaded; no callbacks or trampolines were allocated",
                    &status);
    loaded = 0;
    return 0;
}

s32 attr_module_hidden module_start(s64 argc, const void *args) {
    (void)argc;
    (void)args;
    return 0;
}

s32 attr_module_hidden module_stop(s64 argc, const void *args) {
    (void)argc;
    (void)args;
    return 0;
}
