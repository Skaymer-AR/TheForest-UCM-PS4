#ifndef TFUCM_UNITY_HOST_ADAPTER_H
#define TFUCM_UNITY_HOST_ADAPTER_H

/* Host-only integration contract. This is deliberately not linked into the
 * GoldHEN PRX: the project has not found a Unity-side provider for this API. */

#include "overlay.h"

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

#define UCM_UNITY_HOST_ABI_V1 1u

typedef struct {
    bool connected;
    uint32_t orbis_buttons;
} UcmPadSnapshot;

typedef enum {
    UCM_HOST_DETACH_PENDING = 0,
    UCM_HOST_DETACHED_QUIESCENT,
    UCM_HOST_DETACH_FAILED
} UcmHostDetachResult;

typedef void (*UcmUnityRenderCallback)(void *adapter_context,
                                       const void *render_context);

typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    void *context;
    bool (*register_frame_callback)(void *context,
                                    UcmUnityRenderCallback callback,
                                    void *adapter_context,
                                    uintptr_t *token_out);
    /* Must be nonblocking. DETACHED_QUIESCENT means no callback is executing,
     * queued, or can start after return. PENDING/FAILED retain all state. */
    UcmHostDetachResult (*try_unregister_frame_callback)(void *context,
                                                         uintptr_t token);
    bool (*is_render_context)(void *context, const void *render_context);
    /* Reads a previously published snapshot; must not call ScePad or block. */
    bool (*try_read_pad_snapshot)(void *context, UcmPadSnapshot *snapshot);
    OverlayRenderer renderer;
} UcmUnityHostApi;

typedef enum {
    UCM_ADAPTER_EMPTY = 0,
    UCM_ADAPTER_REGISTERING,
    UCM_ADAPTER_RUNNING,
    UCM_ADAPTER_STOPPING,
    UCM_ADAPTER_DETACHED,
    UCM_ADAPTER_RETAINED
} UcmUnityAdapterState;

typedef enum {
    UCM_ADAPTER_OK = 0,
    UCM_ADAPTER_INVALID,
    UCM_ADAPTER_REGISTER_FAILED,
    UCM_ADAPTER_PENDING,
    UCM_ADAPTER_STOP_RETAINED,
    UCM_ADAPTER_BUSY
} UcmUnityAdapterResult;

typedef struct {
    UcmUnityHostApi host;
    Overlay overlay;
    _Atomic int state;
    _Atomic uint32_t callback_leases;
    atomic_flag stop_gate;
    uintptr_t callback_token;
    bool detach_proven;
} UcmUnityAdapter;

void ucm_unity_adapter_init(UcmUnityAdapter *adapter);
UcmUnityAdapterResult ucm_unity_adapter_start(
    UcmUnityAdapter *adapter, const UcmUnityHostApi *host);
/* Nonblocking. Caller retains adapter storage unless DETACHED is returned. */
UcmUnityAdapterResult ucm_unity_adapter_try_stop(UcmUnityAdapter *adapter);
UcmUnityAdapterState ucm_unity_adapter_state(const UcmUnityAdapter *adapter);

#endif
