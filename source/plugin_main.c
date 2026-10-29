// The Forest CUSA12398 1.15 -- GoldHEN plugin smoke test, not a mod menu.
// No hooks, patches, memory writes or calls to game functions.
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "plugin_common.h"

attr_public const char *g_pluginName = "theforest_ucm_probe";
attr_public const char *g_pluginDesc = "The Forest CUSA12398 1.15 load verification (no hooks)";
attr_public const char *g_pluginAuth = "The Forest UCM PS4 research";
attr_public uint32_t g_pluginVersion = 0x00000300;

static int is_expected_version(const char *version) {
    if (!version) return 0;
    return strcmp(version, "01.15") == 0 || strcmp(version, "1.15") == 0;
}

int32_t attr_public plugin_load(int32_t argc, const char *argv[]) {
    (void)argc; (void)argv;
    struct proc_info procInfo;
    if (sys_sdk_proc_info(&procInfo) != 0) {
        final_printf("[TF-UCM] proc_info unavailable, refusing load.\n");
        return -1;
    }
    if (strcmp(procInfo.titleid, "CUSA12398") != 0 ||
        !is_expected_version(procInfo.version)) {
        final_printf("[TF-UCM] target mismatch: title=%s, version=%s\n",
                     procInfo.titleid, procInfo.version);
        return -1;
    }
    final_printf("[TF-UCM] diagnostic loaded: title=%s version=%s base=0x%lx\n",
                 procInfo.titleid, procInfo.version, procInfo.base_address);
    NotifyStatic(TEX_ICON_SYSTEM, "The Forest: UCM probe loaded (NO HOOKS)");
    return 0;
}
int32_t attr_public plugin_unload(int32_t argc, const char *argv[]) {
    (void)argc; (void)argv;
    final_printf("[TF-UCM] diagnostic unloaded.\n");
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
