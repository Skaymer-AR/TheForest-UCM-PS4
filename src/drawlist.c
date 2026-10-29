#include "drawlist.h"
#include <ctype.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    char code;
    uint8_t rows[7];
} Glyph;

/* 5x7 pixel font. Text is uppercased before lookup to keep the atlas small. */
static const Glyph glyphs[] = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{14,4,4,4,4,4,14}}, {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
    {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
    {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
    {'-',{0,0,0,31,0,0,0}}, {':',{0,4,4,0,4,4,0}},
    {'[',{14,8,8,8,8,8,14}}, {']',{14,2,2,2,2,2,14}},
    {'%',{17,2,4,8,17,0,0}}, {'/',{1,2,2,4,8,8,16}},
    {'+',{0,4,4,31,4,4,0}}, {'|',{4,4,4,4,4,4,4}},
    {'.',{0,0,0,0,0,6,6}}, {'=',{0,31,0,31,0,0,0}},
    {'?',{14,17,1,2,4,0,4}}, {'>',{16,8,4,2,4,8,16}},
    {'<',{1,2,4,8,4,2,1}}, {'_',{0,0,0,0,0,0,31}},
    {'!',{4,4,4,4,4,0,4}}, {'(',{2,4,8,8,8,4,2}},
    {')',{8,4,2,2,2,4,8}}, {'\'',{4,4,2,0,0,0,0}},
    {',',{0,0,0,0,0,4,8}}, {'"',{10,10,5,0,0,0,0}},
    {'#',{10,31,10,10,31,10,0}}, {'&',{12,18,20,8,21,18,13}},
};

static const Glyph *find_glyph(char code) {
    size_t i;
    for (i = 0; i < sizeof(glyphs) / sizeof(glyphs[0]); ++i)
        if (glyphs[i].code == code) return &glyphs[i];
    return NULL;
}

static float channel(uint32_t rgba, unsigned shift) {
    return (float)((rgba >> shift) & 0xffu) / 255.0f;
}

static void push_rect(UcmDrawList *list, float x, float y, float w, float h,
                      uint32_t rgba) {
    UcmVertex v[6];
    float x0, x1, y0, y1;
    float r, g, b, a;
    unsigned i;
    if (!list || !list->vertices || !list->width || !list->height || w <= 0 || h <= 0)
        return;
    if (list->count > list->capacity || list->capacity - list->count < 6) {
        list->overflow = true;
        return;
    }
    x0 = (x * 2.0f / 1280.0f) - 1.0f;
    x1 = ((x + w) * 2.0f / 1280.0f) - 1.0f;
    y0 = 1.0f - (y * 2.0f / 720.0f);
    y1 = 1.0f - ((y + h) * 2.0f / 720.0f);
    r = channel(rgba, 24); g = channel(rgba, 16);
    b = channel(rgba, 8); a = channel(rgba, 0);
    v[0] = (UcmVertex){x0,y0,r,g,b,a}; v[1] = (UcmVertex){x1,y0,r,g,b,a};
    v[2] = (UcmVertex){x1,y1,r,g,b,a}; v[3] = (UcmVertex){x0,y0,r,g,b,a};
    v[4] = (UcmVertex){x1,y1,r,g,b,a}; v[5] = (UcmVertex){x0,y1,r,g,b,a};
    for (i = 0; i < 6; ++i) list->vertices[list->count++] = v[i];
}

static void renderer_rect(void *context, int x, int y, int width, int height,
                          uint32_t rgba) {
    push_rect((UcmDrawList *)context, (float)x, (float)y,
              (float)width, (float)height, rgba);
}

static void renderer_text(void *context, int x, int y, const char *text,
                          uint32_t rgba) {
    UcmDrawList *list = (UcmDrawList *)context;
    int cursor = x;
    const unsigned char *p = (const unsigned char *)text;
    if (!list || !text) return;
    while (*p) {
        char ch;
        const Glyph *glyph;
        unsigned row, col;
        if (p[0] == 0xe2 && p[1] != 0 && p[2] != 0 &&
            p[1] == 0x80 && p[2] == 0x94) {
            push_rect(list, (float)cursor, (float)(y + 6), 20.0f, 2.0f, rgba);
            cursor += 24;
            p += 3;
            continue;
        } else if ((*p & 0xc0) == 0x80) {
            ++p; continue;
        } else {
            ch = (char)*p++;
        }
        ch = (char)toupper((unsigned char)ch);
        if (ch == ' ') { cursor += 12; continue; }
        glyph = find_glyph(ch);
        if (glyph) {
            for (row = 0; row < 7; ++row) {
                for (col = 0; col < 5; ++col) {
                    if (glyph->rows[row] & (1u << (4u - col)))
                        push_rect(list, (float)(cursor + (int)col * 2),
                                  (float)(y + (int)row * 2), 2.0f, 2.0f, rgba);
                }
            }
        }
        cursor += 12;
    }
}

void ucm_drawlist_begin(UcmDrawList *list, UcmVertex *vertices,
                        uint32_t capacity, uint32_t width, uint32_t height) {
    if (!list) return;
    memset(list, 0, sizeof(*list));
    list->vertices = vertices;
    list->capacity = capacity;
    list->width = width;
    list->height = height;
}

OverlayRenderer ucm_drawlist_renderer(UcmDrawList *list) {
    OverlayRenderer renderer = {0};
    renderer.context = list;
    renderer.rect = renderer_rect;
    renderer.text = renderer_text;
    return renderer;
}
