#include "ps4_backend.h"

#include <orbis/Pad.h>
#include <orbis/libkernel.h>

#include "Detour.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/*
 * v0.6 is deliberately a diagnostic-only build. There is no GNM import,
 * command buffer, output-buffer pointer capture, renderer, or framebuffer
 * access in this file. The compile-time profiles below only install passive
 * observers for the named APIs.
 *
 * Profile ids are supplied by scripts/build-prx.sh:
 *   0 passive_all         VideoOut + PadReadState + PadRead
 *   1 videoout_only       VideoOut only
 *   2 pad_read_state_only PadReadState only
 *   3 pad_read_only       PadRead only
 *   4 no_hooks            no detours (load/notification control)
 */
#ifndef UCM_DIAG_PROFILE
#define UCM_DIAG_PROFILE 0
#endif

#if UCM_DIAG_PROFILE == 0
#define UCM_HOOK_VIDEOOUT 1
#define UCM_HOOK_PAD_STATE 1
#define UCM_HOOK_PAD_READ 1
#define UCM_PROFILE_NAME "passive_all"
#elif UCM_DIAG_PROFILE == 1
#define UCM_HOOK_VIDEOOUT 1
#define UCM_HOOK_PAD_STATE 0
#define UCM_HOOK_PAD_READ 0
#define UCM_PROFILE_NAME "videoout_only"
#elif UCM_DIAG_PROFILE == 2
#define UCM_HOOK_VIDEOOUT 0
#define UCM_HOOK_PAD_STATE 1
#define UCM_HOOK_PAD_READ 0
#define UCM_PROFILE_NAME "pad_read_state_only"
#elif UCM_DIAG_PROFILE == 3
#define UCM_HOOK_VIDEOOUT 0
#define UCM_HOOK_PAD_STATE 0
#define UCM_HOOK_PAD_READ 1
#define UCM_PROFILE_NAME "pad_read_only"
#elif UCM_DIAG_PROFILE == 4
#define UCM_HOOK_VIDEOOUT 0
#define UCM_HOOK_PAD_STATE 0
#define UCM_HOOK_PAD_READ 0
#define UCM_PROFILE_NAME "no_hooks"
#else
#error "Unknown UCM_DIAG_PROFILE"
#endif

/* OpenOrbis' VideoOut API declaration has a C++-only enum in video.h, so keep
 * this exact C ABI mirror. Field order/types are from OpenOrbis
 * include/orbis/_types/video.h; the public API is
 * sceVideoOutRegisterBuffers(int32_t, int32_t, void *const *, int32_t,
 * const OrbisVideoOutBufferAttribute *).
 */
typedef struct {
    int32_t format;
    int32_t tmode;
    int32_t aspect;
    uint32_t width;
    uint32_t height;
    uint32_t pixelPitch;
    uint64_t reserved[2];
} UcmVideoOutBufferAttribute;

_Static_assert(sizeof(UcmVideoOutBufferAttribute) == 0x28,
               "OpenOrbis VideoOut attribute ABI mismatch");
_Static_assert(offsetof(UcmVideoOutBufferAttribute, width) == 0x0c,
               "OpenOrbis VideoOut width offset mismatch");
_Static_assert(offsetof(UcmVideoOutBufferAttribute, reserved) == 0x18,
               "OpenOrbis VideoOut reserved offset mismatch");

extern int32_t sceVideoOutRegisterBuffers(
    int32_t handle, int32_t start_index, void *const addresses[],
    int32_t buffer_count, const UcmVideoOutBufferAttribute *attribute);

typedef int32_t (*VideoOutRegisterFn)(
    int32_t, int32_t, void *const *, int32_t,
    const UcmVideoOutBufferAttribute *);
typedef int32_t (*PadReadStateFn)(int32_t, OrbisPadData *);
typedef int32_t (*PadReadFn)(int32_t, OrbisPadData *, int32_t);

static Detour g_videoout_detour;
static Detour g_pad_state_detour;
static Detour g_pad_read_detour;
/* Store call-through stubs as object pointers so they can be published with
 * GCC atomics. GoldHEN's Detour_DetourFunction returns Detour.StubPtr, which
 * contains copied original instructions and a jump back after the patch.
 */
static void *volatile g_videoout_original;
static void *volatile g_pad_state_original;
static void *volatile g_pad_read_original;
static bool g_videoout_hooked;
static bool g_pad_state_hooked;
static bool g_pad_read_hooked;
static bool g_started;
static volatile uint32_t g_active_callbacks;

static volatile uint64_t g_videoout_calls;
static volatile uint64_t g_pad_state_calls;
static volatile uint64_t g_pad_read_calls;
static volatile int32_t g_last_videoout_result;
static volatile int32_t g_last_pad_state_result;
static volatile int32_t g_last_pad_read_result;
static volatile uint32_t g_last_format;
static volatile uint32_t g_last_tmode;
static volatile uint32_t g_last_width;
static volatile uint32_t g_last_height;
static volatile uint32_t g_last_pitch;
static volatile uint32_t g_last_pad_buttons;
static volatile uint32_t g_last_pad_connected;

static void reset_diagnostics(void) {
    __atomic_store_n(&g_active_callbacks, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_videoout_calls, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pad_state_calls, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pad_read_calls, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_videoout_result, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_pad_state_result, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_pad_read_result, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_format, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_tmode, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_width, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_height, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_pitch, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_pad_buttons, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g_last_pad_connected, 0u, __ATOMIC_RELEASE);
}

static void release_detour_storage(Detour *detour) {
    if (detour->StubPtr && detour->StubSize)
        sceKernelMunmap(detour->StubPtr, detour->StubSize);
    if (detour->TrampolinePtr)
        sceKernelMunmap(detour->TrampolinePtr,
                        sizeof(detour->JumpInstructions64));
    memset(detour, 0, sizeof(*detour));
}

static bool install_detour(Detour *detour, uint64_t target, void *hook,
                           void *volatile *original_slot) {
    void *returned_stub;

    Detour_Construct(detour, DetourMode_x64);
    returned_stub = Detour_DetourFunction(detour, target, hook);

    /* If the SDK returned a stub, publish it before validating metadata: its
     * entry jump may already be visible to another game thread.
     */
    if (returned_stub)
        __atomic_store_n(original_slot, returned_stub, __ATOMIC_RELEASE);

    /* The SDK's x64 detour returns the original-call StubPtr, while
     * TrampolinePtr is only the jump relay written at the patched entrypoint.
     * Check every field before publishing the call-through pointer. This
     * also catches a partial allocation failure before treating it as hooked.
     */
    if (!returned_stub || returned_stub != detour->StubPtr ||
        !detour->TrampolinePtr || !detour->StubPtr ||
        detour->Mode != DetourMode_x64 ||
        detour->FunctionPtr != (void *)(uintptr_t)target ||
        detour->HookPtr != hook ||
        detour->StubSize < sizeof(detour->JumpInstructions64)) {
        if (detour->StubPtr) Detour_RestoreFunction(detour);
        if (returned_stub) {
            sceKernelUsleep(100000);
            while (__atomic_load_n(&g_active_callbacks, __ATOMIC_ACQUIRE) != 0u)
                sceKernelUsleep(1000);
        }
        release_detour_storage(detour);
        __atomic_store_n(original_slot, NULL, __ATOMIC_RELEASE);
        return false;
    }

    /* The patched API can be reached by another game thread as soon as the
     * SDK writes its entry jump. The hook waits on this atomic publication if
     * it races the return from Detour_DetourFunction, so it never calls NULL.
     */
    return true;
}

static void remove_detour(Detour *detour, bool *installed) {
    if (*installed) {
        Detour_RestoreFunction(detour);
        *installed = false;
    }
}

static void *wait_for_original(void *volatile *original_slot) {
    void *original;
    while (!(original = __atomic_load_n(original_slot, __ATOMIC_ACQUIRE))) {
        /* Only possible in the short interval between the SDK patching the
         * entrypoint and install_detour publishing the returned call-through.
         */
    }
    return original;
}

#if UCM_HOOK_VIDEOOUT
static int32_t videoout_register_hook(
    int32_t handle, int32_t start_index, void *const addresses[],
    int32_t buffer_count, const UcmVideoOutBufferAttribute *attribute) {
    VideoOutRegisterFn original;
    int32_t result;
    (void)handle;
    (void)start_index;
    (void)addresses;
    (void)buffer_count;

    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    original = (VideoOutRegisterFn)wait_for_original(&g_videoout_original);
    result = original(handle, start_index, addresses, buffer_count, attribute);
    __atomic_add_fetch(&g_videoout_calls, 1u, __ATOMIC_RELAXED);
    __atomic_store_n(&g_last_videoout_result, result, __ATOMIC_RELAXED);
    if (result >= 0 && attribute) {
        __atomic_store_n(&g_last_format, (uint32_t)attribute->format,
                         __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_tmode, (uint32_t)attribute->tmode,
                         __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_width, attribute->width, __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_height, attribute->height, __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_pitch, attribute->pixelPitch,
                         __ATOMIC_RELAXED);
    }
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}
#endif

#if UCM_HOOK_PAD_STATE
static int32_t pad_read_state_hook(int32_t handle, OrbisPadData *data) {
    PadReadStateFn original;
    int32_t result;
    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    original = (PadReadStateFn)wait_for_original(&g_pad_state_original);
    result = original(handle, data);
    __atomic_add_fetch(&g_pad_state_calls, 1u, __ATOMIC_RELAXED);
    __atomic_store_n(&g_last_pad_state_result, result, __ATOMIC_RELAXED);
    if (result >= 0 && data) {
        __atomic_store_n(&g_last_pad_buttons, data->buttons,
                         __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_pad_connected, data->connected,
                         __ATOMIC_RELAXED);
    }
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}
#endif

#if UCM_HOOK_PAD_READ
static int32_t pad_read_hook(int32_t handle, OrbisPadData *data,
                             int32_t count) {
    PadReadFn original;
    int32_t result;
    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    original = (PadReadFn)wait_for_original(&g_pad_read_original);
    result = original(handle, data, count);
    __atomic_add_fetch(&g_pad_read_calls, 1u, __ATOMIC_RELAXED);
    __atomic_store_n(&g_last_pad_read_result, result, __ATOMIC_RELAXED);
    if (result > 0 && data) {
        __atomic_store_n(&g_last_pad_buttons, data->buttons,
                         __ATOMIC_RELAXED);
        __atomic_store_n(&g_last_pad_connected, data->connected,
                         __ATOMIC_RELAXED);
    }
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}
#endif

const char *ps4_backend_profile_name(void) {
    return UCM_PROFILE_NAME;
}

bool ps4_backend_start(void) {
    if (g_started || g_videoout_hooked || g_pad_state_hooked ||
        g_pad_read_hooked) return false;

    memset(&g_videoout_detour, 0, sizeof(g_videoout_detour));
    memset(&g_pad_state_detour, 0, sizeof(g_pad_state_detour));
    memset(&g_pad_read_detour, 0, sizeof(g_pad_read_detour));
    __atomic_store_n(&g_videoout_original, NULL, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pad_state_original, NULL, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pad_read_original, NULL, __ATOMIC_RELEASE);
    reset_diagnostics();

#if UCM_HOOK_VIDEOOUT
    if (!install_detour(&g_videoout_detour,
                        (uint64_t)(uintptr_t)sceVideoOutRegisterBuffers,
                        (void *)videoout_register_hook,
                        &g_videoout_original)) goto fail;
    g_videoout_hooked = true;
#endif

#if UCM_HOOK_PAD_STATE
    if (!install_detour(&g_pad_state_detour,
                        (uint64_t)(uintptr_t)scePadReadState,
                        (void *)pad_read_state_hook,
                        &g_pad_state_original)) goto fail;
    g_pad_state_hooked = true;
#endif

#if UCM_HOOK_PAD_READ
    if (!install_detour(&g_pad_read_detour,
                        (uint64_t)(uintptr_t)scePadRead,
                        (void *)pad_read_hook,
                        &g_pad_read_original)) goto fail;
    g_pad_read_hooked = true;
#endif

    g_started = true;
    return true;

#if UCM_HOOK_VIDEOOUT || UCM_HOOK_PAD_STATE || UCM_HOOK_PAD_READ
fail:
    ps4_backend_stop();
    return false;
#endif
}

void ps4_backend_stop(void) {
    bool had_hooks = g_videoout_hooked || g_pad_state_hooked ||
                     g_pad_read_hooked;

    /* Restore in reverse install order. No callback prints, allocates, waits
     * on a lock, calls Unity, or accesses output-buffer addresses.
     */
    remove_detour(&g_pad_read_detour, &g_pad_read_hooked);
    remove_detour(&g_pad_state_detour, &g_pad_state_hooked);
    remove_detour(&g_videoout_detour, &g_videoout_hooked);

    if (had_hooks) {
        /* GoldHEN exposes no detour in-flight barrier. Let calls already
         * entering a patched function reach their callback, then drain them
         * before freeing either the original-call stub or jump relay.
         */
        sceKernelUsleep(100000);
        while (__atomic_load_n(&g_active_callbacks, __ATOMIC_ACQUIRE) != 0u)
            sceKernelUsleep(1000);
    }

    release_detour_storage(&g_pad_read_detour);
    release_detour_storage(&g_pad_state_detour);
    release_detour_storage(&g_videoout_detour);
    __atomic_store_n(&g_pad_read_original, NULL, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pad_state_original, NULL, __ATOMIC_RELEASE);
    __atomic_store_n(&g_videoout_original, NULL, __ATOMIC_RELEASE);
    g_started = false;
}

void ps4_backend_get_status(Ps4BackendStatus *status) {
    if (!status) return;
    status->profile = UCM_PROFILE_NAME;
    status->videoout_hooked = g_videoout_hooked;
    status->pad_read_state_hooked = g_pad_state_hooked;
    status->pad_read_hooked = g_pad_read_hooked;
    status->videoout_calls = __atomic_load_n(&g_videoout_calls,
                                             __ATOMIC_ACQUIRE);
    status->pad_read_state_calls = __atomic_load_n(&g_pad_state_calls,
                                                   __ATOMIC_ACQUIRE);
    status->pad_read_calls = __atomic_load_n(&g_pad_read_calls,
                                             __ATOMIC_ACQUIRE);
    status->last_videoout_result = __atomic_load_n(&g_last_videoout_result,
                                                   __ATOMIC_ACQUIRE);
    status->last_pad_read_state_result =
        __atomic_load_n(&g_last_pad_state_result, __ATOMIC_ACQUIRE);
    status->last_pad_read_result = __atomic_load_n(&g_last_pad_read_result,
                                                   __ATOMIC_ACQUIRE);
    status->last_format = __atomic_load_n(&g_last_format, __ATOMIC_ACQUIRE);
    status->last_tmode = __atomic_load_n(&g_last_tmode, __ATOMIC_ACQUIRE);
    status->last_width = __atomic_load_n(&g_last_width, __ATOMIC_ACQUIRE);
    status->last_height = __atomic_load_n(&g_last_height, __ATOMIC_ACQUIRE);
    status->last_pitch = __atomic_load_n(&g_last_pitch, __ATOMIC_ACQUIRE);
    status->last_pad_buttons = __atomic_load_n(&g_last_pad_buttons,
                                               __ATOMIC_ACQUIRE);
    status->last_pad_connected = __atomic_load_n(&g_last_pad_connected,
                                                 __ATOMIC_ACQUIRE);
}
