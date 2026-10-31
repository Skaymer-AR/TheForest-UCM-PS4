#include "pad_input_map.h"

#include "overlay.h"

/* Values match OpenOrbis PS4Toolchain/include/orbis/_types/pad.h. */
enum {
    ORBIS_PAD_BUTTON_UP = 0x0010,
    ORBIS_PAD_BUTTON_RIGHT = 0x0020,
    ORBIS_PAD_BUTTON_DOWN = 0x0040,
    ORBIS_PAD_BUTTON_LEFT = 0x0080,
    ORBIS_PAD_BUTTON_L1 = 0x0400,
    ORBIS_PAD_BUTTON_R1 = 0x0800,
    ORBIS_PAD_BUTTON_CIRCLE = 0x2000,
    ORBIS_PAD_BUTTON_CROSS = 0x4000
};

uint32_t ps4_pad_map_buttons(uint32_t buttons, bool connected) {
    uint32_t normalized = 0u;
    if (!connected) return 0u;

    if (buttons & ORBIS_PAD_BUTTON_L1) normalized |= PAD_L1;
    if (buttons & ORBIS_PAD_BUTTON_R1) normalized |= PAD_R1;
    if (buttons & ORBIS_PAD_BUTTON_UP) normalized |= PAD_UP;
    if (buttons & ORBIS_PAD_BUTTON_DOWN) normalized |= PAD_DOWN;
    if (buttons & ORBIS_PAD_BUTTON_LEFT) normalized |= PAD_LEFT;
    if (buttons & ORBIS_PAD_BUTTON_RIGHT) normalized |= PAD_RIGHT;
    if (buttons & ORBIS_PAD_BUTTON_CROSS) normalized |= PAD_CROSS;
    if (buttons & ORBIS_PAD_BUTTON_CIRCLE) normalized |= PAD_CIRCLE;
    return normalized;
}
