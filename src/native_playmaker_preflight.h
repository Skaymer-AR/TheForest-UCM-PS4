#ifndef TFUCM_NATIVE_PLAYMAKER_PREFLIGHT_H
#define TFUCM_NATIVE_PLAYMAKER_PREFLIGHT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Read-only, offline-testable guard for a future title-specific native host.
   NOT a hook installer or a Unity rendering provider. */
#define UCM_PLAYMAKER_GUI_RVA UINT64_C(0x0113FAF0)
#define UCM_PLAYMAKER_PREFIX32_FNV64 UINT64_C(0x4AA4C1EF874F80DC)
#define UCM_PLAYMAKER_PREFIX_SIZE 32u

typedef enum {
    UCM_PREFLIGHT_OK = 0,
    UCM_PREFLIGHT_BAD_TITLE,
    UCM_PREFLIGHT_INVALID_VIEW,
    UCM_PREFLIGHT_WRONG_RANGE,
    UCM_PREFLIGHT_HASH_MISMATCH
} UcmPreflightResult;

typedef struct {
    /* Must be independently verified by the loader through OS module info.
       A guessed base, untrusted pointer or stale ASLR address is NOT valid. */
    uintptr_t module_base;
    uintptr_t executable_start;
    const uint8_t *readable_bytes;
    size_t readable_length;
} UcmExecutableView;

uint64_t ucm_fnv1a64(const uint8_t *data, size_t size);

/* Generic checked view, testable with synthetic memory and expected hash.
   No memory ownership, allocation, patch or system call occurs. */
UcmPreflightResult ucm_preflight_check(
    const char *title_id, const UcmExecutableView *view,
    uintptr_t target_rva, size_t prefix_size, uint64_t expected_hash,
    uintptr_t *target_runtime_address);

/* Locked to the current CUSA12398 historical module's PlayMakerGUI.OnGUI. */
UcmPreflightResult ucm_preflight_playmaker_gui(
    const char *title_id, const UcmExecutableView *view,
    uintptr_t *target_runtime_address);

#endif
