#include "menu.h"

static const char *CATEGORY_NAMES[] = {
  "Cheats", "Environment", "Player", "Animals", "Mutants", "Spawn",
  "Inventory", "Coop", "Dev", "Game"
};

void menu_init(MenuState *state, MenuItem *items, size_t count) {
  size_t i;
  state->visible = false;
  state->category = 0;
  state->items = items;
  state->count = count;
  for (i = 0; i < CAT_COUNT; i++) state->selected[i] = 0;
}
const char *menu_category_name(MenuCategory category) {
  return category >= 0 && category < CAT_COUNT ? CATEGORY_NAMES[category] : "Unknown";
}
size_t menu_category_item_count(const MenuState *state, MenuCategory category) {
  size_t i, total = 0;
  for (i = 0; i < state->count; i++) if (state->items[i].category == category) total++;
  return total;
}
MenuItem *menu_selected(MenuState *state) {
  int at = 0;
  size_t i;
  for (i = 0; i < state->count; i++) {
    if (state->items[i].category != (MenuCategory)state->category) continue;
    if (at++ == state->selected[state->category]) return &state->items[i];
  }
  return NULL;
}
void menu_key(MenuState *state, MenuKey key, MenuCommand callback, void *context) {
  size_t n;
  MenuItem *item;
  if (key == KEY_OPEN) { state->visible = !state->visible; return; }
  if (!state->visible) return;
  if (key == KEY_BACK) { state->visible = false; return; }
  if (key == KEY_NEXT_TAB || key == KEY_PREV_TAB) {
    int dir = key == KEY_NEXT_TAB ? 1 : -1;
    state->category = (state->category + CAT_COUNT + dir) % CAT_COUNT;
    return;
  }
  n = menu_category_item_count(state, (MenuCategory)state->category);
  if (!n) return;
  if (key == KEY_DOWN) { state->selected[state->category] = (state->selected[state->category] + 1) % (int)n; return; }
  if (key == KEY_UP) { state->selected[state->category] = (state->selected[state->category] + (int)n - 1) % (int)n; return; }
  item = menu_selected(state);
  if (!item) return;
  /* Selection is allowed for locked entries; dispatch and value changes are not. */
  if (!item->available) return;
  if (item->kind == MENU_TOGGLE && key == KEY_CONFIRM) item->value = !item->value;
  else if (item->kind == MENU_SLIDER && (key == KEY_LEFT || key == KEY_RIGHT)) {
    int v = item->value + (key == KEY_RIGHT ? item->step : -item->step);
    item->value = v < item->min_value ? item->min_value : v > item->max_value ? item->max_value : v;
  } else if (!(item->kind == MENU_ACTION && key == KEY_CONFIRM)) return;
  /* The host MUST validate version and implement each command. This core never patches memory. */
  if (callback) callback(item->id, item->value, context);
}
