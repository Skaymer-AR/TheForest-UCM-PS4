#include "native_playmaker_preflight.h"
#include <string.h>
#include <limits.h>

uint64_t ucm_fnv1a64(const uint8_t *data, size_t size) {
    uint64_t h = UINT64_C(0xcbf29ce484222325);
    size_t i;
    if (!data && size) return 0;
    for (i = 0; i < size; i++) {
        h ^= data[i];
        h *= UINT64_C(0x100000001b3);
    }
    return h;
}

UcmPreflightResult ucm_preflight_check(
    const char *title_id, const UcmExecutableView *view,
    uintptr_t target_rva, size_t prefix_size, uint64_t expected_hash,
    uintptr_t *target_runtime_address) {
    uintptr_t target, relative;
    if (target_runtime_address) *target_runtime_address = 0;
    if (!title_id || strcmp(title_id, "CUSA12398") != 0)
        return UCM_PREFLIGHT_BAD_TITLE;
    if (!view || !view->readable_bytes || !target_runtime_address ||
        prefix_size == 0 || prefix_size > view->readable_length ||
        view->module_base == 0 || target_rva > UINTPTR_MAX - view->module_base)
        return UCM_PREFLIGHT_INVALID_VIEW;

    target = view->module_base + target_rva;
    if (target < view->executable_start)
        return UCM_PREFLIGHT_WRONG_RANGE;
    relative = target - view->executable_start;
    if (relative > view->readable_length - prefix_size)
        return UCM_PREFLIGHT_WRONG_RANGE;
    if (ucm_fnv1a64(view->readable_bytes + relative, prefix_size) != expected_hash)
        return UCM_PREFLIGHT_HASH_MISMATCH;

    *target_runtime_address = target;
    return UCM_PREFLIGHT_OK;
}

UcmPreflightResult ucm_preflight_playmaker_gui(
    const char *title_id, const UcmExecutableView *view,
    uintptr_t *target_runtime_address) {
    return ucm_preflight_check(
        title_id, view, (uintptr_t)UCM_PLAYMAKER_GUI_RVA,
        UCM_PLAYMAKER_PREFIX_SIZE, UCM_PLAYMAKER_PREFIX32_FNV64,
        target_runtime_address);
}
