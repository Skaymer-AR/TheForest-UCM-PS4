#include "bridge_lifecycle.h"

#include <string.h>

static bool can_accept_callback(BridgeState state) {
    return state == BRIDGE_ARMED || state == BRIDGE_ACTIVE ||
           state == BRIDGE_QUIESCING || state == BRIDGE_DETACHED ||
           state == BRIDGE_RETAINED;
}

void bridge_lifecycle_init(BridgeLifecycle *lifecycle) {
    size_t i;
    if (!lifecycle) return;
    atomic_init(&lifecycle->state, BRIDGE_EMPTY);
    atomic_init(&lifecycle->original, (uintptr_t)0);
    atomic_init(&lifecycle->generation, 1u);
    atomic_init(&lifecycle->next_ticket, 1u);
    for (i = 0; i < BRIDGE_MAX_LEASES; ++i)
        atomic_init(&lifecycle->leases[i], 0u);
    atomic_init(&lifecycle->quiescence_proven, false);
    atomic_init(&lifecycle->target_detached, false);
    atomic_init(&lifecycle->release_count, 0u);
}

BridgeResult bridge_begin_prepare(BridgeLifecycle *lifecycle) {
    int expected = BRIDGE_EMPTY;
    if (!lifecycle) return BRIDGE_INVALID_STATE;
    return atomic_compare_exchange_strong_explicit(
               &lifecycle->state, &expected, BRIDGE_PREPARING,
               memory_order_acq_rel, memory_order_acquire)
               ? BRIDGE_OK : BRIDGE_INVALID_STATE;
}

BridgeResult bridge_publish_original(BridgeLifecycle *lifecycle,
                                     uintptr_t original) {
    int expected = BRIDGE_PREPARING;
    if (!lifecycle || !original) return BRIDGE_NO_ORIGINAL;

    /* Mark the short publication transaction. Teardown returns BUSY while it
     * is in progress rather than racing a write or spinning for it.
     */
    if (!atomic_compare_exchange_strong_explicit(
            &lifecycle->state, &expected, BRIDGE_PUBLISHING,
            memory_order_acq_rel, memory_order_acquire))
        return BRIDGE_INVALID_STATE;

    atomic_store_explicit(&lifecycle->original, original, memory_order_release);
    atomic_store_explicit(&lifecycle->state, BRIDGE_ARMED,
                          memory_order_release);
    return BRIDGE_OK;
}

BridgeResult bridge_activate(BridgeLifecycle *lifecycle) {
    int expected = BRIDGE_ARMED;
    if (!lifecycle) return BRIDGE_INVALID_STATE;
    return atomic_compare_exchange_strong_explicit(
               &lifecycle->state, &expected, BRIDGE_ACTIVE,
               memory_order_acq_rel, memory_order_acquire)
               ? BRIDGE_OK : BRIDGE_INVALID_STATE;
}

BridgeResult bridge_try_enter(BridgeLifecycle *lifecycle, BridgeLease *lease) {
    BridgeState initial;
    uintptr_t original;
    uint64_t generation;
    uint64_t ticket;
    size_t i;

    if (!lifecycle || !lease) return BRIDGE_INVALID_STATE;
    memset(lease, 0, sizeof(*lease));

    initial = (BridgeState)atomic_load_explicit(&lifecycle->state,
                                                memory_order_acquire);
    if (!can_accept_callback(initial) ||
        atomic_load_explicit(&lifecycle->quiescence_proven,
                             memory_order_acquire))
        return BRIDGE_NO_ORIGINAL;

    original = atomic_load_explicit(&lifecycle->original, memory_order_acquire);
    if (!original) return BRIDGE_NO_ORIGINAL;
    generation = atomic_load_explicit(&lifecycle->generation,
                                      memory_order_acquire);
    ticket = atomic_fetch_add_explicit(&lifecycle->next_ticket, 1u,
                                       memory_order_relaxed);
    if (!ticket)
        ticket = atomic_fetch_add_explicit(&lifecycle->next_ticket, 1u,
                                           memory_order_relaxed);

    for (i = 0; i < BRIDGE_MAX_LEASES; ++i) {
        uint64_t empty = 0u;
        if (atomic_compare_exchange_strong_explicit(
                &lifecycle->leases[i], &empty, ticket,
                memory_order_acq_rel, memory_order_relaxed)) {
            BridgeState current = (BridgeState)atomic_load_explicit(
                &lifecycle->state, memory_order_acquire);
            uintptr_t current_original = atomic_load_explicit(
                &lifecycle->original, memory_order_acquire);
            uint64_t current_generation = atomic_load_explicit(
                &lifecycle->generation, memory_order_acquire);
            bool proof = atomic_load_explicit(&lifecycle->quiescence_proven,
                                              memory_order_acquire);

            if (can_accept_callback(current) && !proof &&
                current_original == original &&
                current_generation == generation) {
                lease->generation = generation;
                lease->ticket = ticket;
                lease->slot = (uint32_t)i;
                lease->original = original;
                lease->feature_enabled = current == BRIDGE_ACTIVE;
                lease->held = true;
                return BRIDGE_OK;
            }

            (void)atomic_compare_exchange_strong_explicit(
                &lifecycle->leases[i], &ticket, 0u,
                memory_order_acq_rel, memory_order_relaxed);
            return BRIDGE_NO_ORIGINAL;
        }
    }
    return BRIDGE_NO_SLOT;
}

BridgeResult bridge_leave(BridgeLifecycle *lifecycle, BridgeLease *lease) {
    uint64_t expected;
    if (!lifecycle || !lease || !lease->held || !lease->ticket ||
        lease->slot >= BRIDGE_MAX_LEASES)
        return BRIDGE_STALE_LEASE;
    if (lease->generation != atomic_load_explicit(&lifecycle->generation,
                                                  memory_order_acquire))
        return BRIDGE_STALE_LEASE;

    expected = lease->ticket;
    if (!atomic_compare_exchange_strong_explicit(
            &lifecycle->leases[lease->slot], &expected, 0u,
            memory_order_acq_rel, memory_order_relaxed))
        return BRIDGE_STALE_LEASE;

    lease->held = false;
    lease->original = 0u;
    lease->feature_enabled = false;
    return BRIDGE_OK;
}

BridgeResult bridge_begin_quiesce(BridgeLifecycle *lifecycle) {
    int state, expected;
    if (!lifecycle) return BRIDGE_INVALID_STATE;
    state = atomic_load_explicit(&lifecycle->state, memory_order_acquire);
    if (state == BRIDGE_PUBLISHING) return BRIDGE_BUSY;
    if (state != BRIDGE_PREPARING && state != BRIDGE_ARMED &&
        state != BRIDGE_ACTIVE)
        return BRIDGE_INVALID_STATE;
    expected = state;
    return atomic_compare_exchange_strong_explicit(
               &lifecycle->state, &expected, BRIDGE_QUIESCING,
               memory_order_acq_rel, memory_order_acquire)
               ? BRIDGE_OK : BRIDGE_BUSY;
}

BridgeResult bridge_report_detached(BridgeLifecycle *lifecycle,
                                    bool restore_succeeded) {
    int expected = BRIDGE_QUIESCING;
    if (!lifecycle) return BRIDGE_INVALID_STATE;
    if (!restore_succeeded) {
        return atomic_compare_exchange_strong_explicit(
                   &lifecycle->state, &expected, BRIDGE_RETAINED,
                   memory_order_acq_rel, memory_order_acquire)
                   ? BRIDGE_RESTORE_FAILED : BRIDGE_INVALID_STATE;
    }
    if (!atomic_compare_exchange_strong_explicit(
            &lifecycle->state, &expected, BRIDGE_DETACHED,
            memory_order_acq_rel, memory_order_acquire))
        return BRIDGE_INVALID_STATE;
    atomic_store_explicit(&lifecycle->target_detached, true,
                          memory_order_release);
    return BRIDGE_OK;
}

BridgeResult bridge_confirm_quiescence(BridgeLifecycle *lifecycle,
                                       bool platform_proof) {
    if (!lifecycle || bridge_state(lifecycle) != BRIDGE_DETACHED ||
        !atomic_load_explicit(&lifecycle->target_detached,
                              memory_order_acquire))
        return BRIDGE_INVALID_STATE;
    if (!platform_proof) return BRIDGE_NO_QUIESCENCE_PROOF;
    atomic_store_explicit(&lifecycle->quiescence_proven, true,
                          memory_order_release);
    return BRIDGE_OK;
}

BridgeResult bridge_try_release(BridgeLifecycle *lifecycle) {
    int expected = BRIDGE_DETACHED;
    size_t i;
    if (!lifecycle) return BRIDGE_INVALID_STATE;
    if (bridge_state(lifecycle) == BRIDGE_RETAINED)
        return BRIDGE_RESTORE_FAILED;
    if (bridge_state(lifecycle) != BRIDGE_DETACHED)
        return BRIDGE_INVALID_STATE;
    if (!atomic_load_explicit(&lifecycle->quiescence_proven,
                              memory_order_acquire))
        return BRIDGE_NO_QUIESCENCE_PROOF;
    for (i = 0; i < BRIDGE_MAX_LEASES; ++i) {
        if (atomic_load_explicit(&lifecycle->leases[i],
                                 memory_order_acquire) != 0u)
            return BRIDGE_BUSY;
    }
    if (!atomic_compare_exchange_strong_explicit(
            &lifecycle->state, &expected, BRIDGE_RELEASING,
            memory_order_acq_rel, memory_order_acquire))
        return BRIDGE_BUSY;

    atomic_store_explicit(&lifecycle->original, (uintptr_t)0,
                          memory_order_release);
    atomic_fetch_add_explicit(&lifecycle->release_count, 1u,
                              memory_order_relaxed);
    atomic_store_explicit(&lifecycle->state, BRIDGE_RELEASED,
                          memory_order_release);
    return BRIDGE_OK;
}

BridgeState bridge_state(const BridgeLifecycle *lifecycle) {
    if (!lifecycle) return BRIDGE_EMPTY;
    return (BridgeState)atomic_load_explicit(&lifecycle->state,
                                             memory_order_acquire);
}

uintptr_t bridge_original(const BridgeLifecycle *lifecycle) {
    return lifecycle ? atomic_load_explicit(&lifecycle->original,
                                            memory_order_acquire) : 0u;
}

size_t bridge_in_flight(const BridgeLifecycle *lifecycle) {
    size_t i, count = 0;
    if (!lifecycle) return 0;
    for (i = 0; i < BRIDGE_MAX_LEASES; ++i)
        if (atomic_load_explicit(&lifecycle->leases[i],
                                 memory_order_acquire) != 0u)
            ++count;
    return count;
}

uint64_t bridge_release_count(const BridgeLifecycle *lifecycle) {
    return lifecycle ? atomic_load_explicit(&lifecycle->release_count,
                                             memory_order_acquire) : 0u;
}
