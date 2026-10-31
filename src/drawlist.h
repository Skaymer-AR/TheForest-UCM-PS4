#ifndef TF_UCM_DRAWLIST_H
#define TF_UCM_DRAWLIST_H

#include "overlay.h"
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float x, y;
    float r, g, b, a;
} UcmVertex;

typedef struct {
    UcmVertex *vertices;
    uint32_t capacity;
    uint32_t count;
    uint32_t width;
    uint32_t height;
    bool overflow;
} UcmDrawList;

void ucm_drawlist_begin(UcmDrawList *list, UcmVertex *vertices,
                        uint32_t capacity, uint32_t width, uint32_t height);
OverlayRenderer ucm_drawlist_renderer(UcmDrawList *list);

#endif
