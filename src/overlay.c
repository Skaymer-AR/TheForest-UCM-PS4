#include "overlay.h"
#include <stdio.h>
#include <string.h>

void overlay_init(Overlay *o) {
    memset(o, 0, sizeof(*o));
    o->items[0] = (MenuItem){"god_mode", "God Mode", CAT_CHEATS, MENU_TOGGLE, 0, 0, 1, 1, false};
    o->items[1] = (MenuItem){"infinite_stamina", "Infinite Stamina", CAT_CHEATS, MENU_TOGGLE, 0, 0, 1, 1, false};
    o->items[2] = (MenuItem){"hunger_thirst", "Hunger and Thirst", CAT_PLAYER, MENU_TOGGLE, 0, 0, 1, 1, false};
    o->items[3] = (MenuItem){"free_building", "Build without materials", CAT_GAME, MENU_TOGGLE, 0, 0, 1, 1, false};
    o->items[4] = (MenuItem){"add_inventory", "Add inventory item", CAT_INVENTORY, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[5] = (MenuItem){"teleport", "Teleport player", CAT_PLAYER, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[6] = (MenuItem){"spawn_enemy", "Spawn enemy", CAT_MUTANTS, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[7] = (MenuItem){"spawn_object", "Spawn object", CAT_SPAWN, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[8] = (MenuItem){"time_of_day", "Time of day", CAT_ENVIRONMENT, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[9] = (MenuItem){"weather", "Weather", CAT_ENVIRONMENT, MENU_ACTION, 0, 0, 0, 0, false};
    o->items[10] = (MenuItem){"hints", "Show controls", CAT_DEV, MENU_TOGGLE, 1, 0, 1, 1, true};
    o->items[11] = (MenuItem){"opacity", "Panel opacity (opaque renderer)", CAT_DEV, MENU_SLIDER, 100, 100, 100, 0, false};
    o->items[12] = (MenuItem){"close", "Close menu", CAT_DEV, MENU_ACTION, 0, 0, 0, 0, true};
    menu_init(&o->menu, o->items, OVERLAY_ITEM_COUNT);
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
    r->rect(r->context, 48, 48, 650, 630, 0x122020ffu);
    r->text(r->context, 80, 108, "THE FOREST — ULTIMATE CHEATMENU", 0xffffffffu);
    r->text(r->context, 80, 150, "Game actions stay locked until verified", 0xffd080ffu);
    r->text(r->context, 80, 202, menu_category_name((MenuCategory)o->menu.category), 0x80e0c0ffu);
    for (i = 0; i < o->menu.count; ++i) {
        MenuItem *item = &o->items[i];
        if (item->category != (MenuCategory)o->menu.category) continue;
        if (row == o->menu.selected[o->menu.category])
            r->rect(r->context, 64, 236 + row * 48, 618, 44, 0x346050ffu);
        if (!item->available && strcmp(item->id, "opacity") == 0)
            snprintf(value, sizeof(value), "%s  [UNAVAILABLE]", item->label);
        else if (!item->available)
            snprintf(value, sizeof(value), "%s  [UNVERIFIED]", item->label);
        else if (item->kind == MENU_TOGGLE)
            snprintf(value, sizeof(value), "%s: %s", item->label, item->value ? "ON" : "OFF");
        else if (item->kind == MENU_SLIDER)
            snprintf(value, sizeof(value), "%s: %d%%", item->label, item->value);
        else snprintf(value, sizeof(value), "%s", item->label);
        r->text(r->context, 84, 266 + row * 48, value,
                item->available ? 0xffffffffu : 0x909090ffu);
        ++row;
    }
    if (!row) r->text(r->context, 84, 266, "No entries in this category", 0xb0b0b0ffu);
    if (o->items[10].value) {
        r->text(r->context, 80, 590, "L1+R1 open/close | D-pad select / change", 0xb0b0b0ffu);
        r->text(r->context, 80, 622, "L1/R1 categories | Cross select | Circle back", 0xb0b0b0ffu);
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
