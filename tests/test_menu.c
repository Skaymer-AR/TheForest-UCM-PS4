#include "../src/menu.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static int calls; static void callback(const char *id, int value, void *ctx) { (void)value; (void)ctx; assert(id && *id); calls++; }
int main(void) {
  MenuItem items[] = {
    {"godmode", "God Mode", CAT_CHEATS, MENU_TOGGLE, 0, 0, 1, 1},
    {"speed", "Speed", CAT_CHEATS, MENU_SLIDER, 100, 50, 200, 25},
    {"sleep", "Sleep", CAT_CHEATS, MENU_ACTION, 0, 0, 0, 0},
    {"weather", "Weather", CAT_ENVIRONMENT, MENU_TOGGLE, 0, 0, 1, 1}
  };
  MenuState m; menu_init(&m, items, 4);
  assert(!m.visible); assert(m.category == 0); assert(menu_category_item_count(&m, CAT_CHEATS) == 3);
  menu_key(&m, KEY_CONFIRM, callback, NULL); assert(calls == 0);
  menu_key(&m, KEY_OPEN, callback, NULL); assert(m.visible);
  menu_key(&m, KEY_CONFIRM, callback, NULL); assert(items[0].value == 1 && calls == 1);
  menu_key(&m, KEY_DOWN, callback, NULL); assert(!strcmp(menu_selected(&m)->id,"speed"));
  menu_key(&m, KEY_RIGHT, callback, NULL); assert(items[1].value == 125);
  for (int i=0;i<10;i++)menu_key(&m,KEY_RIGHT,callback,NULL);
  assert(items[1].value == 200);
  menu_key(&m, KEY_DOWN, callback, NULL); menu_key(&m, KEY_CONFIRM, callback, NULL); assert(calls == 13);
  menu_key(&m, KEY_NEXT_TAB, callback, NULL); assert(m.category == CAT_ENVIRONMENT);
  menu_key(&m, KEY_PREV_TAB, callback, NULL); assert(m.category == CAT_CHEATS);
  menu_key(&m, KEY_BACK, callback, NULL); assert(!m.visible);
  printf("Menu core tests: PASS\n");
  return 0;
}
