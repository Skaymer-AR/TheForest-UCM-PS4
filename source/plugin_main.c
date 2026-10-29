// The Forest CUSA12398 1.15 -- native, output-buffer-only UCM overlay.
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "plugin_common.h"
#include "overlay.h"
#include "ps4_backend.h"

static Overlay overlay;
static int loaded;

attr_public const char *g_pluginName = "theforest_ucm";
attr_public const char *g_pluginDesc = "The Forest CUSA12398 1.15 native visual UCM overlay";
attr_public const char *g_pluginAuth = "The Forest UCM PS4 research";
attr_public uint32_t g_pluginVersion = 0x00000500;

static int is_expected_version(const char *version) {
    if (!version) return 0;
    return strcmp(version, "01.15") == 0 || strcmp(version, "1.15") == 0;
}

int32_t attr_public plugin_load(int32_t argc, const char *argv[]) {
    (void)argc; (void)argv;
    if (loaded) return -1;
    struct proc_info procInfo;
    if (sys_sdk_proc_info(&procInfo) != 0) {
        final_printf("[TF-UCM] proc_info unavailable, refusing load.\n");
        return -1;
    }
    if (!memchr(procInfo.titleid, 0, sizeof(procInfo.titleid)) ||
        !memchr(procInfo.version, 0, sizeof(procInfo.version))) return -1;
    if (strcmp(procInfo.titleid, "CUSA12398") != 0 ||
        !is_expected_version(procInfo.version)) {
        final_printf("[TF-UCM] target mismatch: title=%s, version=%s\n",
                     procInfo.titleid, procInfo.version);
        return -1;
    }
    overlay_init(&overlay);
    if (!ps4_backend_start(&overlay)) {
        final_printf("[TF-UCM] could not install verified GNM/VideoOut/Pad adapters; load aborted.\n");
        overlay_stop(&overlay);
        return -1;
    }
    loaded = 1;
    final_printf("[TF-UCM] native overlay adapter installed for title=%s version=%s.\n",
                 procInfo.titleid, procInfo.version);
    NotifyStatic(TEX_ICON_SYSTEM, "The Forest: UCM adapter loaded (L1+R1 in-game)");
    return 0;
}
int32_t attr_public plugin_unload(int32_t argc, const char *argv[]) {
    (void)argc; (void)argv;
    ps4_backend_stop();
    overlay_stop(&overlay);
    loaded = 0;
    final_printf("[TF-UCM] native overlay detached.\n");
    return 0;
}
s32 attr_module_hidden module_start(s64 argc, const void *args) {
    (void)argc; (void)args;
    return 0;
}
s32 attr_module_hidden module_stop(s64 argc, const void *args) {
    (void)argc; (void)args;
    return 0;
}
