#ifndef TF_UCM_MENU_H
#define TF_UCM_MENU_H
#include <stddef.h>
#include <stdbool.h>

typedef enum { MENU_TOGGLE, MENU_ACTION, MENU_SLIDER } MenuKind;
typedef enum { CAT_CHEATS, CAT_ENVIRONMENT, CAT_PLAYER, CAT_ANIMALS, CAT_MUTANTS, CAT_SPAWN, CAT_INVENTORY, CAT_COOP, CAT_DEV, CAT_GAME, CAT_COUNT } MenuCategory;
typedef enum { KEY_OPEN, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_NEXT_TAB, KEY_PREV_TAB, KEY_CONFIRM, KEY_BACK } MenuKey;
typedef struct {
  const char *id, *label;
  MenuCategory category;
  MenuKind kind;
  int value, min_value, max_value, step;
} MenuItem;
typedef struct {
  bool visible;
  int category, selected[CAT_COUNT];
  MenuItem *items;
  size_t count;
} MenuState;
typedef void (*MenuCommand)(const char *id, int value, void *context);

void menu_init(MenuState *state, MenuItem *items, size_t count);
const char *menu_category_name(MenuCategory category);
size_t menu_category_item_count(const MenuState *state, MenuCategory category);
MenuItem *menu_selected(MenuState *state);
void menu_key(MenuState *state, MenuKey key, MenuCommand callback, void *context);
#endif
