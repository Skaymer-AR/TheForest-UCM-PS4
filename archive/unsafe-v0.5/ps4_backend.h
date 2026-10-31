#ifndef TF_UCM_PS4_BACKEND_H
#define TF_UCM_PS4_BACKEND_H

#include <stdbool.h>
#include "overlay.h"

/* Installs GoldHEN detours for VideoOut, GNM submission and passive pad reads.
 * Returns false and rolls back any installed detours if a required hook fails.
 */
bool ps4_backend_start(Overlay *overlay);

/* Detaches hooks, drains callbacks/GPU work and releases owned allocations. */
void ps4_backend_stop(void);

#endif
