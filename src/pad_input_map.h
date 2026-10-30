#ifndef TFUCM_PAD_INPUT_MAP_H
#define TFUCM_PAD_INPUT_MAP_H

#include <stdbool.h>
#include <stdint.h>

/* Pure host-testable mapping from the public OpenOrbis OrbisPadButton mask to
 * the menu's normalized controls. This file does not call ScePad. */
uint32_t ps4_pad_map_buttons(uint32_t orbis_buttons, bool connected);

#endif
