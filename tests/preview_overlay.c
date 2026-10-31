/* Host-only SVG backend for reviewing the actual overlay draw commands. */
#include "overlay.h"
#include <stdio.h>

static void color(uint32_t c) {
    printf("fill=\"#%06x\" fill-opacity=\"%.3f\"", (unsigned)(c >> 8), (c & 255) / 255.0);
}
static void rect(void *ctx, int x, int y, int w, int h, uint32_t c) {
    (void)ctx;
    printf("<rect x=\"%d\" y=\"%d\" width=\"%d\" height=\"%d\" ", x, y, w, h);
    color(c);
    puts("/>");
}
static void text(void *ctx, int x, int y, const char *s, uint32_t c) {
    (void)ctx;
    printf("<text x=\"%d\" y=\"%d\" ", x, y);
    color(c);
    printf(" font-family=\"monospace\" font-size=\"16\">");
    for (; *s; ++s) {
        if (*s == '&') fputs("&amp;", stdout);
        else if (*s == '<') fputs("&lt;", stdout);
        else if (*s == '>') fputs("&gt;", stdout);
        else putchar(*s);
    }
    puts("</text>");
}
int main(void) {
    Overlay o;
    OverlayRenderer r = {NULL, rect, text};
    overlay_init(&o);
    if (!overlay_attach(&o, &r)) return 1;
    puts("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 1280 720\">");
    puts("<rect width=\"1280\" height=\"720\" fill=\"#303838\"/>");
    overlay_frame(&o, true, 0);
    overlay_frame(&o, true, PAD_L1 | PAD_R1);
    puts("</svg>");
    overlay_stop(&o);
    return ferror(stdout) ? 1 : 0;
}
