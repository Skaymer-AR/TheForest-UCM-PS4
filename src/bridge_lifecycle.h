#ifndef TFUCM_BRIDGE_LIFECYCLE_H
#define TFUCM_BRIDGE_LIFECYCLE_H

/* Host-only lifecycle model. This header is intentionally not included by
 * the GoldHEN PRX build. It specifies the ownership contract a future bridge
 * would have to meet before it could be considered for target integration.
 */

#include <stdbool.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>

#define BRIDGE_MAX_LEASES 32u

typedef enum {
    BRIDGE_EMPTY = 0,
    BRIDGE_PREPARING,
    BRIDGE_PUBLISHING,
    BRIDGE_ARMED,
    BRIDGE_ACTIVE,
    BRIDGE_QUIESCING,
    BRIDGE_DETACHED,
    BRIDGE_RETAINED,
    BRIDGE_RELEASING,
    BRIDGE_RELEASED
} BridgeState;

typedef enum {
    BRIDGE_OK = 0,
    BRIDGE_INVALID_STATE,
    BRIDGE_BUSY,
    BRIDGE_NO_ORIGINAL,
    BRIDGE_NO_SLOT,
    BRIDGE_NO_QUIESCENCE_PROOF,
    BRIDGE_RESTORE_FAILED,
    BRIDGE_STALE_LEASE
} BridgeResult;

typedef struct {
    uint64_t generation;
    uint64_t ticket;
    uint32_t slot;
    uintptr_t original;
    bool feature_enabled;
    bool held;
} BridgeLease;

typedef struct {
    _Atomic int state;
    _Atomic uintptr_t original;
    _Atomic uint64_t generation;
    _Atomic uint64_t next_ticket;
    _Atomic uint64_t leases[BRIDGE_MAX_LEASES];
    _Atomic bool quiescence_proven;
    _Atomic bool target_detached;
    _Atomic uint64_t release_count;
} BridgeLifecycle;

void bridge_lifecycle_init(BridgeLifecycle *lifecycle);
BridgeResult bridge_begin_prepare(BridgeLifecycle *lifecycle);
BridgeResult bridge_publish_original(BridgeLifecycle *lifecycle,
                                     uintptr_t original);
BridgeResult bridge_activate(BridgeLifecycle *lifecycle);

/* Nonblocking callback lease API. An ARMED/QUIESCING/DETACHED callback is
 * pass-through only; feature_enabled is true only for an ACTIVE lease.
 */
BridgeResult bridge_try_enter(BridgeLifecycle *lifecycle, BridgeLease *lease);
BridgeResult bridge_leave(BridgeLifecycle *lifecycle, BridgeLease *lease);

/* Shutdown is a sequence of explicit facts. None of these functions waits.
 * restore_succeeded=false permanently retains executable resources.
 * platform_proof=true must mean no thread can still be before or inside the
 * callback (a refcount alone cannot establish that fact).
 */
BridgeResult bridge_begin_quiesce(BridgeLifecycle *lifecycle);
BridgeResult bridge_report_detached(BridgeLifecycle *lifecycle,
                                    bool restore_succeeded);
BridgeResult bridge_confirm_quiescence(BridgeLifecycle *lifecycle,
                                       bool platform_proof);
BridgeResult bridge_try_release(BridgeLifecycle *lifecycle);

BridgeState bridge_state(const BridgeLifecycle *lifecycle);
uintptr_t bridge_original(const BridgeLifecycle *lifecycle);
size_t bridge_in_flight(const BridgeLifecycle *lifecycle);
uint64_t bridge_release_count(const BridgeLifecycle *lifecycle);

#endif
