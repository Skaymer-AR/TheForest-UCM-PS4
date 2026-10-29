#include "overlay.h"
#include <stdio.h>
#include <string.h>

void overlay_init(Overlay *o) {
    memset(o, 0, sizeof(*o));
    o->items[0] = (MenuItem){"hints", "Show controls", CAT_DEV, MENU_TOGGLE, 1, 0, 1, 1};
    o->items[1] = (MenuItem){"opacity", "Panel opacity", CAT_DEV, MENU_SLIDER, 90, 40, 100, 10};
    o->items[2] = (MenuItem){"close", "Close menu", CAT_DEV, MENU_ACTION, 0, 0, 0, 0};
    menu_init(&o->menu, o->items, 3);
    o->menu.category = CAT_DEV;
    o->initialized = true;
}

bool overlay_attach(Overlay *o, const OverlayRenderer *r) {
    if (!o || !o->initialized || o->attached || !r || !r->rect || !r->text) return false;
    o->renderer = *r;
    o->attached = true;
    o->input_ready = false;
    return true;
}

static void draw(Overlay *o) {
    OverlayRenderer *r = &o->renderer;
    char value[96];
    size_t i;
    int row = 0;
    uint32_t alpha = (uint32_t)o->items[1].value * 255u / 100u;
    r->rect(r->context, 64, 64, 520, 540, 0x12202000u | alpha);
    r->text(r->context, 88, 100, "THE FOREST / UCM", 0xffffffffu);
    r->text(r->context, 88, 134, "UI prototype - gameplay unavailable", 0xffd080ffu);
    r->text(r->context, 88, 180, menu_category_name((MenuCategory)o->menu.category), 0x80e0c0ffu);
    for (i = 0; i < o->menu.count; ++i) {
        MenuItem *item = &o->items[i];
        if (item->category != (MenuCategory)o->menu.category) continue;
        if (row == o->menu.selected[o->menu.category])
            r->rect(r->context, 80, 200 + row * 44, 488, 40, 0x346050ffu);
        if (item->kind == MENU_TOGGLE)
            snprintf(value, sizeof(value), "%s: %s", item->label, item->value ? "ON" : "OFF");
        else if (item->kind == MENU_SLIDER)
            snprintf(value, sizeof(value), "%s: %d%%", item->label, item->value);
        else snprintf(value, sizeof(value), "%s", item->label);
        r->text(r->context, 96, 226 + row * 44, value, 0xffffffffu);
        ++row;
    }
    if (!row) r->text(r->context, 96, 240, "No verified gameplay actions", 0xb0b0b0ffu);
    if (o->items[0].value) {
        r->text(r->context, 88, 514, "L1+R1 open/close | D-pad navigate", 0xb0b0b0ffu);
        r->text(r->context, 88, 548, "L1/R1 tabs | Cross select | Circle close", 0xb0b0b0ffu);
    }
}

void overlay_frame(Overlay *o, bool connected, uint32_t buttons) {
    uint32_t pressed, chord = PAD_L1 | PAD_R1;
    if (!o || !o->initialized || !o->attached) return;
    if (!connected) {
        o->menu.visible = false;
        o->input_ready = false;
        o->previous_buttons = 0;
        return;
    }
    /* A neutral sample is mandatory on attach/reconnect; held input is ignored. */
    if (!o->input_ready) {
        if (buttons) return;
        o->input_ready = true;
    }
    pressed = buttons & ~o->previous_buttons;
    if ((buttons & chord) == chord && (o->previous_buttons & chord) != chord)
        menu_key(&o->menu, KEY_OPEN, NULL, NULL);
    else if (o->menu.visible) {
        /* One command per frame, with deterministic priority. No key repeat. */
        if (pressed & PAD_CIRCLE) menu_key(&o->menu, KEY_BACK, NULL, NULL);
        else if (pressed & PAD_UP) menu_key(&o->menu, KEY_UP, NULL, NULL);
        else if (pressed & PAD_DOWN) menu_key(&o->menu, KEY_DOWN, NULL, NULL);
        else if (pressed & PAD_LEFT) menu_key(&o->menu, KEY_LEFT, NULL, NULL);
        else if (pressed & PAD_RIGHT) menu_key(&o->menu, KEY_RIGHT, NULL, NULL);
        else if (pressed & PAD_L1) menu_key(&o->menu, KEY_PREV_TAB, NULL, NULL);
        else if (pressed & PAD_R1) menu_key(&o->menu, KEY_NEXT_TAB, NULL, NULL);
        else if (pressed & PAD_CROSS) {
            MenuItem *item = menu_selected(&o->menu);
            if (item && strcmp(item->id, "close") == 0) o->menu.visible = false;
            else menu_key(&o->menu, KEY_CONFIRM, NULL, NULL);
        }
    }
    o->previous_buttons = buttons;
    if (o->menu.visible) draw(o);
}

void overlay_stop(Overlay *o) {
    if (o) memset(o, 0, sizeof(*o));
}
