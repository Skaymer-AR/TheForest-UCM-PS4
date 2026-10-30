#include "unity_host_adapter.h"

#include "pad_input_map.h"

#include <stddef.h>
#include <string.h>

static bool valid_host(const UcmUnityHostApi *host) {
    return host && host->abi_version == UCM_UNITY_HOST_ABI_V1 &&
           host->struct_size >= sizeof(*host) &&
           host->register_frame_callback &&
           host->try_unregister_frame_callback &&
           host->is_render_context && host->try_read_pad_snapshot &&
           host->renderer.rect && host->renderer.text;
}

void ucm_unity_adapter_init(UcmUnityAdapter *adapter) {
    if (!adapter) return;
    memset(adapter, 0, sizeof(*adapter));
    atomic_init(&adapter->state, UCM_ADAPTER_EMPTY);
    atomic_init(&adapter->callback_leases, 0u);
    atomic_flag_clear(&adapter->stop_gate);
}

static void unity_frame_callback(void *opaque,
                                 const void *render_context) {
    UcmUnityAdapter *adapter = (UcmUnityAdapter *)opaque;
    UcmPadSnapshot snapshot;
    UcmUnityAdapterState state;
    uint32_t buttons = 0u;

    if (!adapter) return;
    atomic_fetch_add_explicit(&adapter->callback_leases, 1u,
                              memory_order_acq_rel);
    state = (UcmUnityAdapterState)atomic_load_explicit(
        &adapter->state, memory_order_acquire);
    if (state != UCM_ADAPTER_RUNNING ||
        !adapter->host.is_render_context(adapter->host.context,
                                         render_context))
        goto done;

    if (!adapter->host.try_read_pad_snapshot(adapter->host.context,
                                             &snapshot)) {
        overlay_frame(&adapter->overlay, false, 0u);
        goto done;
    }
    buttons = ps4_pad_map_buttons(snapshot.orbis_buttons,
                                  snapshot.connected);
    overlay_frame(&adapter->overlay, snapshot.connected, buttons);

done:
    atomic_fetch_sub_explicit(&adapter->callback_leases, 1u,
                              memory_order_release);
}

UcmUnityAdapterResult ucm_unity_adapter_start(
    UcmUnityAdapter *adapter, const UcmUnityHostApi *host) {
    uintptr_t token = 0u;
    int expected = UCM_ADAPTER_EMPTY;
    if (!adapter || !valid_host(host))
        return UCM_ADAPTER_INVALID;
    if (!atomic_compare_exchange_strong_explicit(
            &adapter->state, &expected, UCM_ADAPTER_REGISTERING,
            memory_order_acq_rel, memory_order_acquire))
        return UCM_ADAPTER_INVALID;

    adapter->host = *host;
    overlay_init(&adapter->overlay);
    if (!overlay_attach(&adapter->overlay, &adapter->host.renderer)) {
        overlay_stop(&adapter->overlay);
        memset(&adapter->host, 0, sizeof(adapter->host));
        atomic_store_explicit(&adapter->state, UCM_ADAPTER_EMPTY,
                              memory_order_release);
        return UCM_ADAPTER_INVALID;
    }

    if (!adapter->host.register_frame_callback(
            adapter->host.context, unity_frame_callback, adapter, &token) ||
        token == 0u) {
        /* The host registration contract requires failure to mean that no
         * callback was published. A provider unable to guarantee that must
         * return success with a token and later detach through try_stop(). */
        overlay_stop(&adapter->overlay);
        memset(&adapter->host, 0, sizeof(adapter->host));
        atomic_store_explicit(&adapter->state, UCM_ADAPTER_EMPTY,
                              memory_order_release);
        return UCM_ADAPTER_REGISTER_FAILED;
    }

    adapter->callback_token = token;
    atomic_store_explicit(&adapter->state, UCM_ADAPTER_RUNNING,
                          memory_order_release);
    return UCM_ADAPTER_OK;
}

UcmUnityAdapterResult ucm_unity_adapter_try_stop(UcmUnityAdapter *adapter) {
    UcmUnityAdapterState state;
    UcmHostDetachResult detach_result;
    int expected;

    if (!adapter) return UCM_ADAPTER_INVALID;
    if (atomic_flag_test_and_set_explicit(&adapter->stop_gate,
                                          memory_order_acquire))
        return UCM_ADAPTER_BUSY;

    state = (UcmUnityAdapterState)atomic_load_explicit(
        &adapter->state, memory_order_acquire);
    if (state == UCM_ADAPTER_DETACHED) {
        atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
        return UCM_ADAPTER_OK;
    }
    if (state == UCM_ADAPTER_RETAINED) {
        atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
        return UCM_ADAPTER_STOP_RETAINED;
    }
    if (state == UCM_ADAPTER_RUNNING) {
        expected = UCM_ADAPTER_RUNNING;
        if (!atomic_compare_exchange_strong_explicit(
                &adapter->state, &expected, UCM_ADAPTER_STOPPING,
                memory_order_acq_rel, memory_order_acquire)) {
            atomic_flag_clear_explicit(&adapter->stop_gate,
                                       memory_order_release);
            return UCM_ADAPTER_BUSY;
        }
        state = UCM_ADAPTER_STOPPING;
    }
    if (state != UCM_ADAPTER_STOPPING) {
        atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
        return UCM_ADAPTER_INVALID;
    }

    if (atomic_load_explicit(&adapter->callback_leases,
                             memory_order_acquire) != 0u) {
        atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
        return UCM_ADAPTER_PENDING;
    }

    if (!adapter->detach_proven) {
        detach_result = adapter->host.try_unregister_frame_callback(
            adapter->host.context, adapter->callback_token);
        if (detach_result == UCM_HOST_DETACH_PENDING) {
            atomic_flag_clear_explicit(&adapter->stop_gate,
                                       memory_order_release);
            return UCM_ADAPTER_PENDING;
        }
        if (detach_result != UCM_HOST_DETACHED_QUIESCENT) {
            atomic_store_explicit(&adapter->state, UCM_ADAPTER_RETAINED,
                                  memory_order_release);
            atomic_flag_clear_explicit(&adapter->stop_gate,
                                       memory_order_release);
            return UCM_ADAPTER_STOP_RETAINED;
        }
        adapter->detach_proven = true;
    }

    /* Recheck after the host's proof. If a callback was already in flight,
     * retain storage and let the caller retry; no wait or timeout is used. */
    if (atomic_load_explicit(&adapter->callback_leases,
                             memory_order_acquire) != 0u) {
        atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
        return UCM_ADAPTER_PENDING;
    }

    overlay_stop(&adapter->overlay);
    atomic_store_explicit(&adapter->state, UCM_ADAPTER_DETACHED,
                          memory_order_release);
    atomic_flag_clear_explicit(&adapter->stop_gate, memory_order_release);
    return UCM_ADAPTER_OK;
}

UcmUnityAdapterState ucm_unity_adapter_state(const UcmUnityAdapter *adapter) {
    if (!adapter) return UCM_ADAPTER_EMPTY;
    return (UcmUnityAdapterState)atomic_load_explicit(
        &adapter->state, memory_order_acquire);
}
