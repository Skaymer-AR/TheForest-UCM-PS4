#ifndef TF_UCM_OVERLAY_H
#define TF_UCM_OVERLAY_H
#include "menu.h"
#include <stdint.h>

#define OVERLAY_ITEM_COUNT 13

/* Normalized buttons, NOT ScePad bit values. The platform adapter maps them. */
enum {
    PAD_L1 = 1u << 0, PAD_R1 = 1u << 1, PAD_UP = 1u << 2,
    PAD_DOWN = 1u << 3, PAD_LEFT = 1u << 4, PAD_RIGHT = 1u << 5,
    PAD_CROSS = 1u << 6, PAD_CIRCLE = 1u << 7
};
typedef struct {
    void *context;
    /* Coordinates use a 1280x720 logical canvas; colors are 0xRRGGBBAA.
       Callbacks must consume text synchronously, and must not reenter. */
    void (*rect)(void *, int x, int y, int width, int height, uint32_t rgba);
    void (*text)(void *, int x, int y, const char *, uint32_t rgba);
} OverlayRenderer;

typedef struct {
    MenuState menu;
    MenuItem items[OVERLAY_ITEM_COUNT];
    OverlayRenderer renderer;
    uint32_t previous_buttons;
    bool initialized, attached, input_ready;
} Overlay;

/* All operations belong to one verified frame thread, including stop.
   No allocation, worker threads, game addresses or Unity calls in this core. */
void overlay_init(Overlay *overlay);
/* Caller must first verify the platform renderer/input adapter and thread. */
bool overlay_attach(Overlay *overlay, const OverlayRenderer *renderer);
void overlay_frame(Overlay *overlay, bool pad_connected, uint32_t buttons);
/* Adapter must quiesce frame callbacks before stop or plugin unload. */
void overlay_stop(Overlay *overlay);
#endif
