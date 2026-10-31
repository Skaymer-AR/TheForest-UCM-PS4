#ifndef TF_UCM_PS4_BACKEND_H
#define TF_UCM_PS4_BACKEND_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    const char *profile;
    bool hooks_active;
    bool renderer_active;
    bool framebuffer_writes_active;
    bool controller_interception_active;
    bool gameplay_writes_active;
} Ps4BackendStatus;

/* Safety-hold backend: this build owns no hooks, renderer or game state. */
bool ps4_backend_start(void);
void ps4_backend_stop(void);
void ps4_backend_get_status(Ps4BackendStatus *status);
const char *ps4_backend_profile_name(void);

#endif
