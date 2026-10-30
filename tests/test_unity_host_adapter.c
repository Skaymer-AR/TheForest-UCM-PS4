#include "overlay.h"
#include "pad_input_map.h"
#include "unity_host_adapter.h"

#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { \
    if (!(x)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); \
        return 1; \
    } \
} while (0)

enum {
    ORBIS_UP = 0x0010,
    ORBIS_RIGHT = 0x0020,
    ORBIS_DOWN = 0x0040,
    ORBIS_LEFT = 0x0080,
    ORBIS_L1 = 0x0400,
    ORBIS_R1 = 0x0800,
    ORBIS_CIRCLE = 0x2000,
    ORBIS_CROSS = 0x4000,
    ORBIS_TRIANGLE = 0x1000
};

typedef struct {
    UcmUnityRenderCallback callback;
    void *callback_context;
    uintptr_t token;
    void *valid_render_context;
    UcmPadSnapshot sample;
    UcmHostDetachResult detach_result;
    bool registration_ok;
    bool invoke_during_registration;
    bool connected_sample_ok;
    bool block_read;
    _Atomic bool read_entered;
    _Atomic bool release_read;
    _Atomic uint32_t read_count;
    _Atomic uint32_t unregister_count;
    _Atomic uint32_t rect_count;
    _Atomic uint32_t text_count;
    bool title_seen;
} FakeHost;

static void fake_rect(void *context, int x, int y, int width, int height,
                      uint32_t rgba) {
    FakeHost *fake = context;
    (void)x; (void)y; (void)width; (void)height; (void)rgba;
    atomic_fetch_add(&fake->rect_count, 1u);
}

static void fake_text(void *context, int x, int y, const char *text,
                      uint32_t rgba) {
    FakeHost *fake = context;
    (void)x; (void)y; (void)rgba;
    if (strcmp(text, "THE FOREST — ULTIMATE CHEATMENU") == 0)
        fake->title_seen = true;
    atomic_fetch_add(&fake->text_count, 1u);
}

static bool fake_register(void *context, UcmUnityRenderCallback callback,
                          void *adapter_context, uintptr_t *token_out) {
    FakeHost *fake = context;
    if (!fake->registration_ok) return false;
    fake->callback = callback;
    fake->callback_context = adapter_context;
    fake->token = 42u;
    *token_out = fake->token;
    if (fake->invoke_during_registration)
        callback(adapter_context, fake->valid_render_context);
    return true;
}

static UcmHostDetachResult fake_unregister(void *context, uintptr_t token) {
    FakeHost *fake = context;
    atomic_fetch_add(&fake->unregister_count, 1u);
    if (token != fake->token) return UCM_HOST_DETACH_FAILED;
    return fake->detach_result;
}

static bool fake_is_render(void *context, const void *render_context) {
    FakeHost *fake = context;
    return render_context == fake->valid_render_context;
}

static bool fake_read_snapshot(void *context, UcmPadSnapshot *snapshot) {
    FakeHost *fake = context;
    atomic_fetch_add(&fake->read_count, 1u);
    if (fake->block_read) {
        atomic_store(&fake->read_entered, true);
        while (!atomic_load(&fake->release_read)) sched_yield();
    }
    if (!fake->connected_sample_ok) return false;
    *snapshot = fake->sample;
    return true;
}

static void fake_init(FakeHost *fake, UcmUnityHostApi *api) {
    memset(fake, 0, sizeof(*fake));
    fake->valid_render_context = fake;
    fake->detach_result = UCM_HOST_DETACHED_QUIESCENT;
    fake->registration_ok = true;
    fake->connected_sample_ok = true;
    fake->sample.connected = true;
    atomic_init(&fake->read_entered, false);
    atomic_init(&fake->release_read, false);
    atomic_init(&fake->read_count, 0u);
    atomic_init(&fake->unregister_count, 0u);
    atomic_init(&fake->rect_count, 0u);
    atomic_init(&fake->text_count, 0u);
    memset(api, 0, sizeof(*api));
    api->abi_version = UCM_UNITY_HOST_ABI_V1;
    api->struct_size = sizeof(*api);
    api->context = fake;
    api->register_frame_callback = fake_register;
    api->try_unregister_frame_callback = fake_unregister;
    api->is_render_context = fake_is_render;
    api->try_read_pad_snapshot = fake_read_snapshot;
    api->renderer.context = fake;
    api->renderer.rect = fake_rect;
    api->renderer.text = fake_text;
}

static void invoke_frame(FakeHost *fake, const void *render_context) {
    if (fake->callback)
        fake->callback(fake->callback_context, render_context);
}

static int test_pad_mapping(void) {
    uint32_t mapped = ps4_pad_map_buttons(
        ORBIS_L1 | ORBIS_R1 | ORBIS_UP | ORBIS_DOWN | ORBIS_LEFT |
        ORBIS_RIGHT | ORBIS_CROSS | ORBIS_CIRCLE | ORBIS_TRIANGLE, true);
    CHECK(mapped == (PAD_L1 | PAD_R1 | PAD_UP | PAD_DOWN | PAD_LEFT |
                     PAD_RIGHT | PAD_CROSS | PAD_CIRCLE));
    CHECK(ps4_pad_map_buttons(0xFFFFFFFFu, false) == 0u);
    CHECK(ps4_pad_map_buttons(ORBIS_TRIANGLE, true) == 0u);
    return 0;
}

static int test_start_validation_and_registration_failure(void) {
    FakeHost fake;
    UcmUnityHostApi api;
    UcmUnityAdapter adapter;
    fake_init(&fake, &api);
    ucm_unity_adapter_init(&adapter);

    api.struct_size--;
    CHECK(ucm_unity_adapter_start(&adapter, &api) == UCM_ADAPTER_INVALID);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_EMPTY);
    api.struct_size = sizeof(api);
    fake.registration_ok = false;
    CHECK(ucm_unity_adapter_start(&adapter, &api) == UCM_ADAPTER_REGISTER_FAILED);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_EMPTY);
    CHECK(atomic_load(&fake.read_count) == 0u);
    return 0;
}

static int test_render_context_navigation_and_stop(void) {
    FakeHost fake;
    UcmUnityHostApi api;
    UcmUnityAdapter adapter;
    uint32_t reads;

    fake_init(&fake, &api);
    fake.invoke_during_registration = true;
    ucm_unity_adapter_init(&adapter);
    CHECK(ucm_unity_adapter_start(&adapter, &api) == UCM_ADAPTER_OK);
    CHECK(atomic_load(&fake.read_count) == 0u);

    invoke_frame(&fake, (const void *)(uintptr_t)0xBADu);
    CHECK(atomic_load(&fake.read_count) == 0u);
    CHECK(atomic_load(&fake.rect_count) == 0u);

    fake.sample.orbis_buttons = 0u;
    invoke_frame(&fake, fake.valid_render_context); /* neutral attach sample */
    fake.sample.orbis_buttons = ORBIS_L1 | ORBIS_R1;
    invoke_frame(&fake, fake.valid_render_context);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_RUNNING);
    CHECK(fake.title_seen);
    CHECK(atomic_load(&fake.rect_count) > 0u);

    fake.sample.orbis_buttons = ORBIS_DOWN;
    invoke_frame(&fake, fake.valid_render_context);
    CHECK(adapter.overlay.menu.selected[CAT_CHEATS] == 1);
    fake.sample.orbis_buttons = ORBIS_R1;
    invoke_frame(&fake, fake.valid_render_context);
    CHECK(adapter.overlay.menu.category == CAT_ENVIRONMENT);
    fake.sample.orbis_buttons = ORBIS_CIRCLE;
    invoke_frame(&fake, fake.valid_render_context);
    CHECK(!adapter.overlay.menu.visible);

    reads = atomic_load(&fake.read_count);

    fake.detach_result = UCM_HOST_DETACH_PENDING;
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_PENDING);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_STOPPING);
    invoke_frame(&fake, fake.valid_render_context);
    CHECK(atomic_load(&fake.read_count) == reads);

    fake.detach_result = UCM_HOST_DETACHED_QUIESCENT;
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_OK);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_DETACHED);
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_OK);
    return 0;
}

typedef struct {
    FakeHost *fake;
} CallbackThreadArgs;

static void *run_callback(void *opaque) {
    CallbackThreadArgs *args = opaque;
    invoke_frame(args->fake, args->fake->valid_render_context);
    return NULL;
}

static int test_inflight_callback_is_not_waited_on_or_detached(void) {
    FakeHost fake;
    UcmUnityHostApi api;
    UcmUnityAdapter adapter;
    CallbackThreadArgs args;
    pthread_t thread;
    unsigned int spins;

    fake_init(&fake, &api);
    fake.block_read = true;
    ucm_unity_adapter_init(&adapter);
    CHECK(ucm_unity_adapter_start(&adapter, &api) == UCM_ADAPTER_OK);
    args.fake = &fake;
    CHECK(pthread_create(&thread, NULL, run_callback, &args) == 0);
    for (spins = 0; spins < 1000000u && !atomic_load(&fake.read_entered); ++spins)
        sched_yield();
    if (!atomic_load(&fake.read_entered)) {
        atomic_store(&fake.release_read, true);
        (void)pthread_join(thread, NULL);
        CHECK(false);
    }

    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_PENDING);
    CHECK(atomic_load(&fake.unregister_count) == 0u);
    atomic_store(&fake.release_read, true);
    CHECK(pthread_join(thread, NULL) == 0);
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_OK);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_DETACHED);
    CHECK(atomic_load(&fake.unregister_count) == 1u);
    return 0;
}

static int test_failed_detach_retains_adapter(void) {
    FakeHost fake;
    UcmUnityHostApi api;
    UcmUnityAdapter adapter;

    fake_init(&fake, &api);
    fake.detach_result = UCM_HOST_DETACH_FAILED;
    ucm_unity_adapter_init(&adapter);
    CHECK(ucm_unity_adapter_start(&adapter, &api) == UCM_ADAPTER_OK);
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_STOP_RETAINED);
    CHECK(ucm_unity_adapter_state(&adapter) == UCM_ADAPTER_RETAINED);
    CHECK(ucm_unity_adapter_try_stop(&adapter) == UCM_ADAPTER_STOP_RETAINED);
    CHECK(atomic_load(&fake.unregister_count) == 1u);
    return 0;
}

int main(void) {
    if (test_pad_mapping() || test_start_validation_and_registration_failure() ||
        test_render_context_navigation_and_stop() ||
        test_inflight_callback_is_not_waited_on_or_detached() ||
        test_failed_detach_retains_adapter())
        return 1;
    puts("Unity host adapter and DS4 mapper tests: PASS");
    return 0;
}
