#include "overlay.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int rects, texts, saw_title, saw_empty;
static void rect(void *ctx, int x, int y, int w, int h, uint32_t color) {
    (void)ctx; (void)color;
    assert(x >= 0 && y >= 0 && x + w <= 1280 && y + h <= 720);
    ++rects;
}
static void text(void *ctx, int x, int y, const char *s, uint32_t color) {
    (void)ctx; (void)color;
    assert(x >= 0 && y >= 0 && x < 1280 && y < 720 && s && *s);
    if (strstr(s, "THE FOREST")) saw_title = 1;
    if (strstr(s, "No verified")) saw_empty = 1;
    ++texts;
}
static void press(Overlay *o, uint32_t b) {
    overlay_frame(o, true, 0);
    overlay_frame(o, true, b);
}
int main(void) {
    Overlay o;
    OverlayRenderer r = {NULL, rect, text}, invalid = {NULL, rect, NULL};
    memset(&o, 0, sizeof(o));
    assert(!overlay_attach(&o, &r));
    overlay_init(&o);
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    assert(!o.menu.visible && rects == 0);
    assert(!overlay_attach(&o, &invalid));
    assert(overlay_attach(&o, &r));
    assert(!overlay_attach(&o, &r));
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    assert(!o.menu.visible); /* Held at attachment. */
    press(&o, PAD_L1 | PAD_R1);
    assert(o.menu.visible && saw_title && rects == 2 && texts > 0);
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    assert(o.menu.visible); /* Holding does not toggle repeatedly. */
    press(&o, PAD_CROSS);
    assert(o.items[0].value == 0);
    overlay_frame(&o, true, PAD_CROSS);
    assert(o.items[0].value == 0);
    press(&o, PAD_DOWN);
    assert(o.menu.selected[CAT_DEV] == 1);
    for (int i = 0; i < 12; ++i) press(&o, PAD_RIGHT);
    assert(o.items[1].value == 100);
    for (int i = 0; i < 12; ++i) press(&o, PAD_LEFT);
    assert(o.items[1].value == 40);
    press(&o, PAD_R1);
    assert(o.menu.category == CAT_GAME && saw_empty);
    press(&o, PAD_R1);
    assert(o.menu.category == CAT_CHEATS);
    press(&o, PAD_L1);
    press(&o, PAD_L1);
    assert(o.menu.category == CAT_DEV);
    press(&o, PAD_DOWN);
    press(&o, PAD_CROSS);
    assert(!o.menu.visible); /* Close action is UI-only. */
    press(&o, PAD_L1 | PAD_R1);
    press(&o, PAD_CIRCLE);
    assert(!o.menu.visible);
    press(&o, PAD_L1 | PAD_R1);
    overlay_frame(&o, false, PAD_L1 | PAD_R1);
    assert(!o.menu.visible && !o.input_ready);
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    assert(!o.menu.visible);
    press(&o, PAD_L1 | PAD_R1);
    assert(o.menu.visible);
    overlay_stop(&o);
    rects = texts = 0;
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    assert(!o.attached && !o.initialized && !rects && !texts);
    overlay_stop(&o);
    overlay_init(&o);
    assert(overlay_attach(&o, &r));
    puts("Overlay input, rendering and lifecycle tests: PASS");
    return 0;
}
