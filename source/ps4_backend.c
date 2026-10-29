// Safety hotfix v0.7: compile-only NO-HOOK baseline.
// All API detours from v0.5/v0.6 are quarantined in Git history.
// Do not restore inline hooks without independent safety review.
#include "ps4_backend.h"

#if defined(UCM_DIAG_PROFILE) && UCM_DIAG_PROFILE != 4
#error "Unsafe hook profile disabled after full PS4 lockup. Use no_hooks (4)."
#endif

static const Ps4BackendStatus g_safe_status = {
    .profile = "no_hooks",
    .failed_hook = "none",
    .videoout_hooked = false,
    .pad_read_state_hooked = false,
    .pad_read_hooked = false
};

bool ps4_backend_start(void) {
    /* Intentionally no detours, framebuffer access or controller interception. */
    return true;
}

void ps4_backend_stop(void) {
    /* No callbacks, trampolines or shared allocations to wait for or release. */
}

void ps4_backend_get_status(Ps4BackendStatus *status) {
    if (status) *status = g_safe_status;
}

const char *ps4_backend_profile_name(void) {
    return "no_hooks";
}
