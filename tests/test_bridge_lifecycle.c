#define _GNU_SOURCE
#include "bridge_lifecycle.h"

#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdio.h>
#include <time.h>

#define TEST_ORIGINAL ((uintptr_t)0x12345000u)
#define SPIN_LIMIT 5000000u

static void start_and_activate(BridgeLifecycle *lifecycle) {
    assert(bridge_begin_prepare(lifecycle) == BRIDGE_OK);
    assert(bridge_publish_original(lifecycle, TEST_ORIGINAL) == BRIDGE_OK);
    assert(bridge_activate(lifecycle) == BRIDGE_OK);
}

static bool wait_flag(const atomic_bool *flag) {
    unsigned i;
    for (i = 0; i < SPIN_LIMIT; ++i) {
        if (atomic_load_explicit(flag, memory_order_acquire)) return true;
        if ((i & 0x3ffu) == 0u) sched_yield();
    }
    return false;
}

static bool wait_count(const atomic_uint *value, unsigned minimum) {
    unsigned i;
    for (i = 0; i < SPIN_LIMIT; ++i) {
        if (atomic_load_explicit(value, memory_order_acquire) >= minimum)
            return true;
        if ((i & 0x3ffu) == 0u) sched_yield();
    }
    return false;
}

static int timed_join(pthread_t thread) {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += 3;
    return pthread_timedjoin_np(thread, NULL, &deadline);
}

static void test_missing_original_is_bounded(void) {
    BridgeLifecycle lifecycle;
    BridgeLease lease;
    bridge_lifecycle_init(&lifecycle);
    assert(bridge_begin_prepare(&lifecycle) == BRIDGE_OK);
    assert(bridge_try_enter(&lifecycle, &lease) == BRIDGE_NO_ORIGINAL);
    assert(bridge_publish_original(&lifecycle, 0u) == BRIDGE_NO_ORIGINAL);
    assert(bridge_state(&lifecycle) == BRIDGE_PREPARING);
    assert(bridge_begin_quiesce(&lifecycle) == BRIDGE_OK);
    assert(bridge_report_detached(&lifecycle, true) == BRIDGE_OK);
    assert(bridge_confirm_quiescence(&lifecycle, true) == BRIDGE_OK);
    assert(bridge_try_release(&lifecycle) == BRIDGE_OK);
}

static void test_interrupted_initialization(void) {
    BridgeLifecycle before_original, before_exposure;
    BridgeLease lease;

    bridge_lifecycle_init(&before_original);
    assert(bridge_begin_prepare(&before_original) == BRIDGE_OK);
    assert(bridge_begin_quiesce(&before_original) == BRIDGE_OK);
    assert(bridge_report_detached(&before_original, true) == BRIDGE_OK);
    assert(bridge_confirm_quiescence(&before_original, true) == BRIDGE_OK);
    assert(bridge_try_release(&before_original) == BRIDGE_OK);

    bridge_lifecycle_init(&before_exposure);
    assert(bridge_begin_prepare(&before_exposure) == BRIDGE_OK);
    assert(bridge_publish_original(&before_exposure, TEST_ORIGINAL) == BRIDGE_OK);
    /* An armed callback is pass-through only while installation is staged. */
    assert(bridge_try_enter(&before_exposure, &lease) == BRIDGE_OK);
    assert(lease.original == TEST_ORIGINAL && !lease.feature_enabled);
    assert(bridge_leave(&before_exposure, &lease) == BRIDGE_OK);
    assert(bridge_begin_quiesce(&before_exposure) == BRIDGE_OK);
    assert(bridge_report_detached(&before_exposure, true) == BRIDGE_OK);
    assert(bridge_confirm_quiescence(&before_exposure, true) == BRIDGE_OK);
    assert(bridge_try_release(&before_exposure) == BRIDGE_OK);
}

static void test_unload_requires_restore_quiescence_and_no_leases(void) {
    BridgeLifecycle lifecycle;
    BridgeLease lease, stale_copy;
    bridge_lifecycle_init(&lifecycle);
    start_and_activate(&lifecycle);

    assert(bridge_try_enter(&lifecycle, &lease) == BRIDGE_OK);
    assert(lease.feature_enabled && lease.original == TEST_ORIGINAL);
    stale_copy = lease;
    assert(bridge_begin_quiesce(&lifecycle) == BRIDGE_OK);
    assert(bridge_report_detached(&lifecycle, true) == BRIDGE_OK);
    assert(bridge_confirm_quiescence(&lifecycle, false) ==
           BRIDGE_NO_QUIESCENCE_PROOF);
    assert(bridge_try_release(&lifecycle) == BRIDGE_NO_QUIESCENCE_PROOF);
    assert(bridge_original(&lifecycle) == TEST_ORIGINAL);

    assert(bridge_confirm_quiescence(&lifecycle, true) == BRIDGE_OK);
    assert(bridge_try_release(&lifecycle) == BRIDGE_BUSY);
    assert(bridge_original(&lifecycle) == TEST_ORIGINAL);
    assert(bridge_leave(&lifecycle, &lease) == BRIDGE_OK);
    assert(bridge_leave(&lifecycle, &stale_copy) == BRIDGE_STALE_LEASE);
    assert(bridge_try_release(&lifecycle) == BRIDGE_OK);

    assert(bridge_try_enter(&lifecycle, &lease) == BRIDGE_NO_ORIGINAL);
    assert(bridge_leave(&lifecycle, &stale_copy) == BRIDGE_STALE_LEASE);
    assert(bridge_release_count(&lifecycle) == 1u);
}

static void test_failed_restore_retains_resources(void) {
    BridgeLifecycle lifecycle;
    bridge_lifecycle_init(&lifecycle);
    start_and_activate(&lifecycle);
    assert(bridge_begin_quiesce(&lifecycle) == BRIDGE_OK);
    assert(bridge_report_detached(&lifecycle, false) == BRIDGE_RESTORE_FAILED);
    assert(bridge_state(&lifecycle) == BRIDGE_RETAINED);
    assert(bridge_original(&lifecycle) == TEST_ORIGINAL);
    assert(bridge_try_release(&lifecycle) == BRIDGE_RESTORE_FAILED);
    assert(bridge_release_count(&lifecycle) == 0u);
    {
        BridgeLease lease;
        assert(bridge_try_enter(&lifecycle, &lease) == BRIDGE_OK);
        assert(!lease.feature_enabled && lease.original == TEST_ORIGINAL);
        assert(bridge_leave(&lifecycle, &lease) == BRIDGE_OK);
    }
}

typedef struct {
    BridgeLifecycle lifecycle;
    atomic_bool install_go;
    atomic_bool armed;
    atomic_bool activate_go;
    atomic_bool activated;
    atomic_bool callback_started;
    atomic_bool callback_held;
    atomic_bool release_callback;
    atomic_bool callback_done;
    atomic_bool unload_done;
    atomic_uint callback_entries;
    atomic_uint pass_through_entries;
    atomic_uint wait_failures;
    BridgeResult unload_release_result;
} ConcurrentCase;

static void *installer_thread(void *arg) {
    ConcurrentCase *test = arg;
    if (!wait_flag(&test->install_go)) {
        atomic_fetch_add(&test->wait_failures, 1u);
        return NULL;
    }
    if (bridge_begin_prepare(&test->lifecycle) != BRIDGE_OK ||
        bridge_publish_original(&test->lifecycle, TEST_ORIGINAL) != BRIDGE_OK) {
        atomic_fetch_add(&test->wait_failures, 1u);
        return NULL;
    }
    atomic_store_explicit(&test->armed, true, memory_order_release);
    if (!wait_flag(&test->activate_go) ||
        bridge_activate(&test->lifecycle) != BRIDGE_OK) {
        atomic_fetch_add(&test->wait_failures, 1u);
        return NULL;
    }
    atomic_store_explicit(&test->activated, true, memory_order_release);
    return NULL;
}

static void *callback_thread(void *arg) {
    ConcurrentCase *test = arg;
    unsigned i;
    atomic_store_explicit(&test->callback_started, true, memory_order_release);
    for (i = 0; i < SPIN_LIMIT; ++i) {
        BridgeLease lease;
        BridgeResult result = bridge_try_enter(&test->lifecycle, &lease);
        if (result == BRIDGE_OK) {
            if (lease.feature_enabled) {
                atomic_fetch_add_explicit(&test->callback_entries, 1u,
                                          memory_order_relaxed);
                atomic_store_explicit(&test->callback_held, true,
                                      memory_order_release);
                if (!wait_flag(&test->release_callback))
                    atomic_fetch_add(&test->wait_failures, 1u);
                if (bridge_leave(&test->lifecycle, &lease) != BRIDGE_OK)
                    atomic_fetch_add(&test->wait_failures, 1u);
                atomic_store_explicit(&test->callback_done, true,
                                      memory_order_release);
                return NULL;
            }
            atomic_fetch_add_explicit(&test->pass_through_entries, 1u,
                                      memory_order_relaxed);
            if (bridge_leave(&test->lifecycle, &lease) != BRIDGE_OK)
                atomic_fetch_add(&test->wait_failures, 1u);
        }
        if (atomic_load_explicit(&test->callback_done, memory_order_acquire))
            return NULL;
    }
    atomic_fetch_add(&test->wait_failures, 1u);
    return NULL;
}

static void *unloader_thread(void *arg) {
    ConcurrentCase *test = arg;
    if (!wait_flag(&test->callback_held)) {
        atomic_fetch_add(&test->wait_failures, 1u);
        return NULL;
    }
    if (bridge_begin_quiesce(&test->lifecycle) != BRIDGE_OK ||
        bridge_report_detached(&test->lifecycle, true) != BRIDGE_OK) {
        atomic_fetch_add(&test->wait_failures, 1u);
        return NULL;
    }
    test->unload_release_result = bridge_try_release(&test->lifecycle);
    atomic_store_explicit(&test->unload_done, true, memory_order_release);
    return NULL;
}

static void test_concurrent_install_callback_unload(void) {
    ConcurrentCase test;
    pthread_t installer, callback, unloader;

    bridge_lifecycle_init(&test.lifecycle);
    atomic_init(&test.install_go, false);
    atomic_init(&test.armed, false);
    atomic_init(&test.activate_go, false);
    atomic_init(&test.activated, false);
    atomic_init(&test.callback_started, false);
    atomic_init(&test.callback_held, false);
    atomic_init(&test.release_callback, false);
    atomic_init(&test.callback_done, false);
    atomic_init(&test.unload_done, false);
    atomic_init(&test.callback_entries, 0u);
    atomic_init(&test.pass_through_entries, 0u);
    atomic_init(&test.wait_failures, 0u);
    test.unload_release_result = BRIDGE_INVALID_STATE;

    assert(pthread_create(&callback, NULL, callback_thread, &test) == 0);
    assert(pthread_create(&installer, NULL, installer_thread, &test) == 0);
    assert(wait_flag(&test.callback_started));
    assert(pthread_create(&unloader, NULL, unloader_thread, &test) == 0);

    atomic_store_explicit(&test.install_go, true, memory_order_release);
    assert(wait_flag(&test.armed));
    /* Exercise calls in the armed/pass-through window before activation. */
    assert(wait_count(&test.pass_through_entries, 1u));
    atomic_store_explicit(&test.activate_go, true, memory_order_release);
    assert(wait_flag(&test.activated));
    assert(wait_flag(&test.callback_held));
    assert(wait_flag(&test.unload_done));
    assert(test.unload_release_result == BRIDGE_NO_QUIESCENCE_PROOF);
    assert(bridge_original(&test.lifecycle) == TEST_ORIGINAL);
    assert(bridge_in_flight(&test.lifecycle) == 1u);

    atomic_store_explicit(&test.release_callback, true, memory_order_release);
    assert(timed_join(callback) == 0);
    assert(timed_join(installer) == 0);
    assert(timed_join(unloader) == 0);
    assert(atomic_load(&test.wait_failures) == 0u);
    assert(atomic_load(&test.callback_entries) > 0u);
    assert(atomic_load(&test.pass_through_entries) > 0u);
    assert(bridge_in_flight(&test.lifecycle) == 0u);

    /* Joining the callback worker stands in for a separately supplied,
     * platform-level quiescence proof; the model never infers it from count.
     */
    assert(bridge_confirm_quiescence(&test.lifecycle, true) == BRIDGE_OK);
    assert(bridge_try_release(&test.lifecycle) == BRIDGE_OK);
}

int main(void) {
    test_missing_original_is_bounded();
    test_interrupted_initialization();
    test_unload_requires_restore_quiescence_and_no_leases();
    test_failed_restore_retains_resources();
    test_concurrent_install_callback_unload();
    puts("Bridge lifecycle fault-injection tests: PASS");
    return 0;
}
