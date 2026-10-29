// The Forest CUSA12398 1.15 -- v0.6 startup-hook diagnostic PRX.
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "plugin_common.h"
#include "ps4_backend.h"

static int loaded;

attr_public const char *g_pluginName = "theforest_ucm_diag";
attr_public const char *g_pluginDesc =
    "The Forest UCM hook diagnostic; GNM and rendering disabled";
attr_public const char *g_pluginAuth = "The Forest UCM PS4 research";
attr_public uint32_t g_pluginVersion = 0x00000600;

static int is_expected_version(const char *version) {
    if (!version) return 0;
    return strcmp(version, "01.15") == 0 || strcmp(version, "1.15") == 0;
}

static const char *enabled(bool value) {
    return value ? "ON" : "OFF";
}

static void log_hook_profile(const char *event,
                             const Ps4BackendStatus *status) {
    final_printf(
        "[TF-UCM-DIAG] %s profile=%s GNM=OFF render=OFF framebuffer=OFF "
        "VideoOut=%s PadReadState=%s PadRead=%s\n",
        event, status->profile, enabled(status->videoout_hooked),
        enabled(status->pad_read_state_hooked),
        enabled(status->pad_read_hooked));
}

static void log_callback_summary(const Ps4BackendStatus *status) {
    final_printf(
        "[TF-UCM-DIAG] callbacks profile=%s VideoOut=%llu(result=%d,"
        "%ux%u pitch=%u format=0x%08x tmode=%u) "
        "PadReadState=%llu(result=%d) PadRead=%llu(result=%d) "
        "pad_connected=%u buttons=0x%08x\n",
        status->profile,
        (unsigned long long)status->videoout_calls,
        status->last_videoout_result, status->last_width,
        status->last_height, status->last_pitch, status->last_format,
        status->last_tmode,
        (unsigned long long)status->pad_read_state_calls,
        status->last_pad_read_state_result,
        (unsigned long long)status->pad_read_calls,
        status->last_pad_read_result, status->last_pad_connected,
        status->last_pad_buttons);
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
        log_hook_profile("install failed and rolled back", &status);
        return -1;
    }

    loaded = 1;
    ps4_backend_get_status(&status);
    log_hook_profile("loaded", &status);
    NotifyStatic(TEX_ICON_SYSTEM,
                 "The Forest: UCM diagnostic (GNM/render OFF)");
    return 0;
}

int32_t attr_public plugin_unload(int32_t argc, const char *argv[]) {
    Ps4BackendStatus status;
    (void)argc;
    (void)argv;

    ps4_backend_stop();
    ps4_backend_get_status(&status);
    log_callback_summary(&status);
    final_printf("[TF-UCM-DIAG] hooks restored; no graphics resources owned.\n");
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
