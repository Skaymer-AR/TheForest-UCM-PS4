#include "native_playmaker_preflight.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_checked_synthetic_view(void) {
    uint8_t fake[96];
    UcmExecutableView view;
    uintptr_t out;
    uint64_t expected;
    memset(fake, 0xA5, sizeof(fake));
    view.module_base = (uintptr_t)0x10000000;
    view.executable_start = view.module_base + (uintptr_t)0x100;
    view.readable_bytes = fake;
    view.readable_length = sizeof(fake);
    expected = ucm_fnv1a64(fake + 16, 32);
    assert(expected != 0);
    assert(ucm_fnv1a64(fake + 16, 32) == expected);
    assert(ucm_preflight_check("CUSA12398", &view, 0x110, 32,
                               expected, &out) == UCM_PREFLIGHT_OK);
    assert(out == view.module_base + 0x110);
    assert(ucm_preflight_check("CUSA00000", &view, 0x110, 32,
                               expected, &out) == UCM_PREFLIGHT_BAD_TITLE);
    assert(out == 0);
    assert(ucm_preflight_check("CUSA12398", &view, 0x10, 32,
                               expected, &out) == UCM_PREFLIGHT_WRONG_RANGE);
    assert(ucm_preflight_check("CUSA12398", &view, 0x180, 32,
                               expected, &out) == UCM_PREFLIGHT_WRONG_RANGE);
    assert(ucm_preflight_check("CUSA12398", &view, 0x110, 32,
                               expected ^ 1, &out) == UCM_PREFLIGHT_HASH_MISMATCH);
    fake[16] ^= 1;
    assert(ucm_preflight_check("CUSA12398", &view, 0x110, 32,
                               expected, &out) == UCM_PREFLIGHT_HASH_MISMATCH);
    assert(out == 0);
    view.module_base = UINTPTR_MAX - 4;
    assert(ucm_preflight_check("CUSA12398", &view, 0x110, 32,
                               expected, &out) == UCM_PREFLIGHT_INVALID_VIEW);
}

static void test_fixed_build_gate_refuses_synthetic_code(void) {
    uint8_t fake[64] = {0};
    UcmExecutableView view;
    uintptr_t out = 1;
    view.module_base = (uintptr_t)0x10000000;
    view.executable_start = view.module_base + (uintptr_t)UCM_PLAYMAKER_GUI_RVA;
    view.readable_bytes = fake;
    view.readable_length = sizeof(fake);
    assert(ucm_preflight_playmaker_gui("CUSA12398", &view, &out) ==
           UCM_PREFLIGHT_HASH_MISMATCH);
    assert(out == 0);
}

int main(void) {
    test_checked_synthetic_view();
    test_fixed_build_gate_refuses_synthetic_code();
    puts("PlayMakerGUI native preflight: PASS (no hooks or memory writes)");
    return 0;
}
