#ifndef TF_UCM_PS4_BACKEND_H
#define TF_UCM_PS4_BACKEND_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    const char *profile;
    const char *failed_hook;
    bool videoout_hooked;
    bool pad_read_state_hooked;
    bool pad_read_hooked;
    uint64_t videoout_calls;
    uint64_t pad_read_state_calls;
    uint64_t pad_read_calls;
    int32_t last_videoout_result;
    int32_t last_pad_read_state_result;
    int32_t last_pad_read_result;
    uint32_t last_format;
    uint32_t last_tmode;
    uint32_t last_width;
    uint32_t last_height;
    uint32_t last_pitch;
    uint32_t last_pad_buttons;
    uint32_t last_pad_connected;
} Ps4BackendStatus;

/* Diagnostic profiles install only passive API observers. All profiles have
 * GNM, rendering, framebuffer writes and gameplay changes disabled.
 */
bool ps4_backend_start(void);
void ps4_backend_stop(void);
void ps4_backend_get_status(Ps4BackendStatus *status);
const char *ps4_backend_profile_name(void);

#endif
