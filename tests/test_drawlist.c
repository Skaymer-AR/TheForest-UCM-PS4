#include "drawlist.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static int nearly(float a, float b) { return fabsf(a - b) < 0.0001f; }

int main(void) {
    UcmVertex vertices[1024];
    UcmDrawList list;
    OverlayRenderer renderer;

    ucm_drawlist_begin(&list, vertices, 1024, 1920, 1080);
    renderer = ucm_drawlist_renderer(&list);
    renderer.rect(renderer.context, 0, 0, 1280, 720, 0xff804020u);
    assert(list.count == 6 && !list.overflow);
    assert(nearly(vertices[0].x, -1.0f));
    assert(nearly(vertices[0].y, 1.0f));
    assert(nearly(vertices[2].x, 1.0f));
    assert(nearly(vertices[2].y, -1.0f));
    assert(nearly(vertices[0].r, 1.0f));
    assert(nearly(vertices[0].g, 128.0f / 255.0f));
    assert(nearly(vertices[0].a, 32.0f / 255.0f));

    ucm_drawlist_begin(&list, vertices, 1024, 1920, 1080);
    renderer = ucm_drawlist_renderer(&list);
    renderer.text(renderer.context, 0, 0, "A — R1", 0xffffffffu);
    assert(list.count > 6 && list.count % 6 == 0 && !list.overflow);

    ucm_drawlist_begin(&list, vertices, 5, 1920, 1080);
    renderer = ucm_drawlist_renderer(&list);
    renderer.rect(renderer.context, 0, 0, 10, 10, 0xffffffffu);
    assert(list.count == 0 && list.overflow);

    puts("drawlist tests passed");
    return 0;
}
