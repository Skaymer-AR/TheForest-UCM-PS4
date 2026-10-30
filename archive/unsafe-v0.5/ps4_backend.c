#include "ps4_backend.h"

#include <orbis/Pad.h>
#include <orbis/GnmDriver.h>
#include <orbis/libkernel.h>
#include <gnm_drawcommandbuffer.h>
#include <gpuaddr.h>
#include <gnm_helpers.h>
#include <gnm_dataformat.h>
#include <platform.h>

#include "Common.h"
#include "Detour.h"
#include "Utilities.h"
#include "drawlist.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* The C version of OpenOrbis' VideoOut.h includes fixed-underlying-type enum
 * syntax accepted only in C++. Keep this ABI mirror in C and validate it
 * against the public OpenOrbis field layout in docs/OVERLAY.md.
 */
typedef struct {
    int32_t format;
    int32_t tmode;
    int32_t aspect;
    uint32_t width;
    uint32_t height;
    uint32_t pixelPitch;
    uint64_t reserved[2];
} UcmVideoOutBufferAttribute;
_Static_assert(sizeof(UcmVideoOutBufferAttribute) == 0x28,
               "OpenOrbis VideoOut attribute ABI mismatch");

extern int32_t sceVideoOutRegisterBuffers(
    int32_t handle, int32_t start_index, void *const addresses[],
    int32_t buffer_count, const UcmVideoOutBufferAttribute *attribute);

#define UCM_VIDEO_FORMAT_A8B8G8R8_SRGB ((int32_t)0x80002200u)
#define UCM_VIDEO_TMODE_TILE 0
#define UCM_VIDEO_TMODE_LINEAR 1
#define UCM_MAX_OUTPUTS 8
#define UCM_MAX_BUFFERS 8
#define UCM_MAX_GAME_DCBS 16
#define UCM_MAX_FILL_RUNS 30000
#define UCM_DCB_BYTES (2u * 1024u * 1024u)
#define UCM_DCB_ALIGNMENT 0x10000u
#define UCM_DCB_MEMORY_TYPE 3
#define UCM_DISPLAY_MICROTILE_WIDTH 8u
#define UCM_DISPLAY_MICROTILE_HEIGHT 8u

typedef struct {
    uint64_t offset;
    uint32_t size;
    uint32_t value;
} FillRun;

typedef struct {
    bool supported;
    bool linear;
    uint32_t width;
    uint32_t height;
    uint32_t pitch;
    uint64_t surface_size;
    GpaSurfaceContext context;
    uint32_t generation;
} DisplaySurface;

typedef struct {
    bool used;
    int32_t handle;
    int32_t buffer_count;
    UcmVideoOutBufferAttribute attribute;
    void *buffers[UCM_MAX_BUFFERS];
    DisplaySurface surface;
} VideoOutput;

typedef struct {
    void *mapped;
    off_t direct_offset;
    size_t size;
    volatile uint64_t *eop_label;
    bool allocated;
    bool mapped_ok;
    bool in_flight;
} DirectDcb;

typedef int32_t (*SubmitAndFlipFn)(
    uint32_t, void **, uint32_t *, void **, uint32_t *, uint32_t, uint32_t,
    uint32_t, uint64_t);
typedef int32_t (*VideoOutRegisterFn)(
    int32_t, int32_t, void *const *, int32_t,
    const UcmVideoOutBufferAttribute *);
typedef int32_t (*PadReadStateFn)(int32_t, OrbisPadData *);
typedef int32_t (*PadReadFn)(int32_t, OrbisPadData *, int32_t);

static Overlay *g_overlay;
static OverlayRenderer g_renderer;
static UcmDrawList g_drawlist;
static UcmVertex g_vertices[65536];
static FillRun g_fill_runs[UCM_MAX_FILL_RUNS];
static uint32_t g_fill_run_count;
static uint64_t g_fill_cache_hash;
static uint32_t g_fill_cache_generation;
static bool g_fill_cache_valid;

static VideoOutput g_outputs[UCM_MAX_OUTPUTS];
static volatile uint32_t g_output_lock;
static volatile uint32_t g_submit_lock;
static volatile uint32_t g_stop_requested;
static volatile uint32_t g_active_callbacks;
static volatile uint64_t g_pad_state;
static uint32_t g_next_surface_generation;
static DirectDcb g_dcb;

static Detour g_submit_detour;
static Detour g_videoout_detour;
static Detour g_pad_state_detour;
static Detour g_pad_read_detour;
static SubmitAndFlipFn g_submit_original;
static VideoOutRegisterFn g_videoout_original;
static PadReadStateFn g_pad_state_original;
static PadReadFn g_pad_read_original;
static bool g_submit_hooked;
static bool g_videoout_hooked;
static bool g_pad_state_hooked;
static bool g_pad_read_hooked;

static void lock_word(volatile uint32_t *word) {
    while (__atomic_exchange_n(word, 1u, __ATOMIC_ACQUIRE) != 0u) {
        /* Registration is rare; submit uses a try-lock and never spins here. */
    }
}

static void unlock_word(volatile uint32_t *word) {
    __atomic_store_n(word, 0u, __ATOMIC_RELEASE);
}

static bool try_lock_word(volatile uint32_t *word) {
    return __atomic_exchange_n(word, 1u, __ATOMIC_ACQUIRE) == 0u;
}

static uint32_t map_pad_buttons(uint32_t buttons) {
    uint32_t mapped = 0;
    if (buttons & ORBIS_PAD_BUTTON_L1) mapped |= PAD_L1;
    if (buttons & ORBIS_PAD_BUTTON_R1) mapped |= PAD_R1;
    if (buttons & ORBIS_PAD_BUTTON_UP) mapped |= PAD_UP;
    if (buttons & ORBIS_PAD_BUTTON_DOWN) mapped |= PAD_DOWN;
    if (buttons & ORBIS_PAD_BUTTON_LEFT) mapped |= PAD_LEFT;
    if (buttons & ORBIS_PAD_BUTTON_RIGHT) mapped |= PAD_RIGHT;
    if (buttons & ORBIS_PAD_BUTTON_CROSS) mapped |= PAD_CROSS;
    if (buttons & ORBIS_PAD_BUTTON_CIRCLE) mapped |= PAD_CIRCLE;
    return mapped;
}

static void publish_pad(const OrbisPadData *data) {
    uint64_t packed;
    if (!data) return;
    packed = (uint64_t)(data->connected ? 1u : 0u) << 32;
    packed |= map_pad_buttons(data->buttons);
    __atomic_store_n(&g_pad_state, packed, __ATOMIC_RELEASE);
}

static bool setup_display_surface(const UcmVideoOutBufferAttribute *attribute,
                                  DisplaySurface *out) {
    GnmGpuMode gpu_mode;
    GnmTileMode tilemode;
    GpaTextureInfo texture;
    GpaTilingParams tiling;
    GpaSurfaceInfo surface_info;
    GpaSurfaceProperties properties;

    if (!attribute || !out) return false;
    memset(out, 0, sizeof(*out));
    if (attribute->format != UCM_VIDEO_FORMAT_A8B8G8R8_SRGB ||
        attribute->width < 640 || attribute->height < 360 ||
        attribute->width > 1920 || attribute->height > 1080 ||
        attribute->pixelPitch < attribute->width ||
        attribute->pixelPitch > 2048) return false;

    out->width = attribute->width;
    out->height = attribute->height;
    out->pitch = attribute->pixelPitch;
    out->generation = __atomic_add_fetch(&g_next_surface_generation, 1u,
                                          __ATOMIC_ACQ_REL);

    if (attribute->tmode == UCM_VIDEO_TMODE_LINEAR) {
        out->linear = true;
        out->surface_size = (uint64_t)attribute->pixelPitch *
                            (uint64_t)attribute->height * 4u;
        out->supported = true;
        return true;
    }
    if (attribute->tmode != UCM_VIDEO_TMODE_TILE) return false;

    gpu_mode = sceGnmGpuMode();
    if (sceGpaFindOptimalSurface(&properties, GPA_SURFACE_COLORDISPLAY,
                                 32, 1, false, gpu_mode) != GPA_ERR_OK)
        return false;
    tilemode = properties.tilemode;
    memset(&texture, 0, sizeof(texture));
    texture.type = GNM_TEXTURE_2D;
    texture.fmt = GNM_FMT_R8G8B8A8_SRGB;
    texture.width = attribute->pixelPitch;
    texture.height = attribute->height;
    texture.pitch = attribute->pixelPitch;
    texture.depth = 1;
    texture.numfrags = 1;
    texture.nummips = 1;
    texture.numslices = 1;
    texture.tm = tilemode;
    texture.mingpumode = gpu_mode;
    texture.pow2pad = false;

    memset(&tiling, 0, sizeof(tiling));
    if (sceGpaTpInit(&tiling, &texture, 0, 0) != GPA_ERR_OK ||
        sceGpaComputeSurfaceInfo(&surface_info, &tiling) != GPA_ERR_OK ||
        surface_info.pitch != attribute->pixelPitch ||
        surface_info.surfacesize > UINT32_MAX ||
        sceGpaInitSurfaceContext(&out->context,
                                (size_t)surface_info.surfacesize,
                                &tiling) != GPA_ERR_OK) return false;

    out->surface_size = surface_info.surfacesize;
    out->linear = false;
    out->supported = true;
    return true;
}

static int output_index_for(int32_t handle) {
    int i;
    for (i = 0; i < UCM_MAX_OUTPUTS; ++i)
        if (g_outputs[i].used && g_outputs[i].handle == handle) return i;
    return -1;
}

static int free_output_index(void) {
    int i;
    for (i = 0; i < UCM_MAX_OUTPUTS; ++i)
        if (!g_outputs[i].used) return i;
    return -1;
}

static int32_t videoout_register_hook(
    int32_t handle, int32_t start_index, void *const addresses[],
    int32_t buffer_count, const UcmVideoOutBufferAttribute *attribute) {
    DisplaySurface surface;
    bool supported;
    int32_t result;
    int output_index;
    int i;

    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    result = g_videoout_original(handle, start_index, addresses,
                                 buffer_count, attribute);
    if (result >= 0 && !__atomic_load_n(&g_stop_requested, __ATOMIC_ACQUIRE) &&
        attribute && addresses && buffer_count > 0 && start_index >= 0 &&
        start_index + buffer_count <= UCM_MAX_BUFFERS) {
        supported = setup_display_surface(attribute, &surface);
        lock_word(&g_output_lock);
        output_index = output_index_for(handle);
        if (output_index < 0) output_index = free_output_index();
        if (output_index >= 0) {
            VideoOutput *output = &g_outputs[output_index];
            if (!output->used || output->handle != handle ||
                memcmp(&output->attribute, attribute, sizeof(*attribute)) != 0) {
                memset(output, 0, sizeof(*output));
                output->used = true;
                output->handle = handle;
                output->attribute = *attribute;
                output->surface = surface;
                output->surface.supported = supported;
                output->buffer_count = UCM_MAX_BUFFERS;
            } else {
                /* A new set of addresses has the same layout, but invalidate
                 * the draw cache so a future surface change cannot reuse it.
                 */
                output->surface = surface;
                output->surface.supported = supported;
            }
            for (i = 0; i < buffer_count; ++i)
                output->buffers[start_index + i] = addresses[i];
        }
        unlock_word(&g_output_lock);
        if (!supported) {
            printf("[TF-UCM] VideoOut handle %d: unsupported format/mode/pitch; renderer skipped.\n",
                   handle);
        } else {
            printf("[TF-UCM] VideoOut handle %d mapped %ux%u pitch=%u mode=%s.\n",
                   handle, attribute->width, attribute->height,
                   attribute->pixelPitch,
                   attribute->tmode == UCM_VIDEO_TMODE_LINEAR ? "linear" : "tile");
        }
    }
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}

static int32_t pad_read_state_hook(int32_t handle, OrbisPadData *data) {
    int32_t result;
    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    result = g_pad_state_original(handle, data);
    if (result >= 0 && data) publish_pad(data);
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}

static int32_t pad_read_hook(int32_t handle, OrbisPadData *data, int32_t count) {
    int32_t result;
    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    result = g_pad_read_original(handle, data, count);
    if (result > 0 && data) publish_pad(data);
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}

static bool append_run(uint64_t offset, uint32_t size, uint32_t value) {
    if (!size || (offset & 3u) || (size & 3u) ||
        g_fill_run_count >= UCM_MAX_FILL_RUNS) return false;
    g_fill_runs[g_fill_run_count++] = (FillRun){offset, size, value};
    return true;
}

static uint32_t rgba_to_memory_word(const UcmVertex *vertex) {
    uint32_t r = (uint32_t)(vertex->r * 255.0f + 0.5f);
    uint32_t g = (uint32_t)(vertex->g * 255.0f + 0.5f);
    uint32_t b = (uint32_t)(vertex->b * 255.0f + 0.5f);
    /* VideoOut A8B8G8R8_SRGB stores bytes in R,G,B,A order on little endian. */
    return (r & 0xffu) | ((g & 0xffu) << 8) | ((b & 0xffu) << 16) |
           0xff000000u;
}

static uint64_t surface_offset(const DisplaySurface *surface,
                               uint32_t x, uint32_t y, bool *ok) {
    uint64_t offset = 0;
    uint64_t bit_offset = 0;
    *ok = false;
    if (surface->linear) {
        offset = ((uint64_t)y * surface->pitch + x) * 4u;
        *ok = offset + 4u <= surface->surface_size;
        return offset;
    }
    if (sceGpaComputeSurfaceCoord(&offset, &bit_offset, &surface->context,
                                  x, y, 0, 0) != GPA_ERR_OK || bit_offset != 0 ||
        offset + 4u > surface->surface_size) return 0;
    *ok = true;
    return offset;
}

static bool append_tile_pixels(const DisplaySurface *surface,
                               uint32_t left, uint32_t top,
                               uint32_t right, uint32_t bottom,
                               uint32_t value) {
    uint64_t offsets[UCM_DISPLAY_MICROTILE_WIDTH *
                     UCM_DISPLAY_MICROTILE_HEIGHT];
    uint32_t count = 0;
    uint32_t x, y, i;

    for (y = top; y < bottom; ++y) {
        for (x = left; x < right; ++x) {
            bool ok;
            uint64_t offset = surface_offset(surface, x, y, &ok);
            if (!ok || count >= UCM_DISPLAY_MICROTILE_WIDTH *
                                UCM_DISPLAY_MICROTILE_HEIGHT) return false;
            i = count++;
            while (i > 0 && offsets[i - 1] > offset) {
                offsets[i] = offsets[i - 1];
                --i;
            }
            offsets[i] = offset;
        }
    }
    if (!count) return true;

    {
        uint64_t begin = offsets[0];
        uint32_t pixels = 1;
        for (i = 1; i < count; ++i) {
            if (offsets[i] == begin + (uint64_t)pixels * 4u) {
                ++pixels;
            } else {
                if (!append_run(begin, pixels * 4u, value)) return false;
                begin = offsets[i];
                pixels = 1;
            }
        }
        return append_run(begin, pixels * 4u, value);
    }
}

static bool append_rectangle(const DisplaySurface *surface,
                             int logical_x, int logical_y,
                             int logical_right, int logical_bottom,
                             uint32_t value) {
    int x0 = logical_x, y0 = logical_y;
    int x1 = logical_right, y1 = logical_bottom;
    uint32_t sx0, sy0, sx1, sy1;

    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > 1280) x1 = 1280;
    if (y1 > 720) y1 = 720;
    if (x1 <= x0 || y1 <= y0) return true;

    sx0 = (uint32_t)(((uint64_t)x0 * surface->width) / 1280u);
    sy0 = (uint32_t)(((uint64_t)y0 * surface->height) / 720u);
    sx1 = (uint32_t)(((uint64_t)x1 * surface->width + 1279u) / 1280u);
    sy1 = (uint32_t)(((uint64_t)y1 * surface->height + 719u) / 720u);
    if (sx1 > surface->width) sx1 = surface->width;
    if (sy1 > surface->height) sy1 = surface->height;
    if (sx1 <= sx0 || sy1 <= sy0) return true;

    if (surface->linear) {
        uint32_t y;
        uint32_t byte_count = (sx1 - sx0) * 4u;
        for (y = sy0; y < sy1; ++y) {
            uint64_t offset = ((uint64_t)y * surface->pitch + sx0) * 4u;
            if (offset + byte_count > surface->surface_size ||
                !append_run(offset, byte_count, value)) return false;
        }
        return true;
    }

    {
        uint32_t tile_y;
        uint32_t tile_x;
        for (tile_y = (sy0 / UCM_DISPLAY_MICROTILE_HEIGHT) *
                      UCM_DISPLAY_MICROTILE_HEIGHT;
             tile_y < sy1; tile_y += UCM_DISPLAY_MICROTILE_HEIGHT) {
            uint32_t bottom = tile_y + UCM_DISPLAY_MICROTILE_HEIGHT;
            uint32_t part_top = sy0 > tile_y ? sy0 : tile_y;
            uint32_t part_bottom;
            if (bottom > surface->height) bottom = surface->height;
            part_bottom = sy1 < bottom ? sy1 : bottom;
            for (tile_x = (sx0 / UCM_DISPLAY_MICROTILE_WIDTH) *
                          UCM_DISPLAY_MICROTILE_WIDTH;
                 tile_x < sx1; tile_x += UCM_DISPLAY_MICROTILE_WIDTH) {
                uint32_t right = tile_x + UCM_DISPLAY_MICROTILE_WIDTH;
                uint32_t part_left = sx0 > tile_x ? sx0 : tile_x;
                uint32_t part_right;
                bool full;
                bool ok;
                uint64_t offset;
                if (right > surface->width) right = surface->width;
                part_right = sx1 < right ? sx1 : right;
                full = part_left == tile_x && part_top == tile_y &&
                       part_right == tile_x + UCM_DISPLAY_MICROTILE_WIDTH &&
                       part_bottom == tile_y + UCM_DISPLAY_MICROTILE_HEIGHT &&
                       tile_x + UCM_DISPLAY_MICROTILE_WIDTH <= surface->width &&
                       tile_y + UCM_DISPLAY_MICROTILE_HEIGHT <= surface->height;
                if (full) {
                    offset = surface_offset(surface, tile_x, tile_y, &ok);
                    if (ok && (offset & 255u) == 0 &&
                        offset + 256u <= surface->surface_size) {
                        if (!append_run(offset, 256u, value)) return false;
                        continue;
                    }
                }
                if (!append_tile_pixels(surface, part_left, part_top,
                                        part_right, part_bottom, value))
                    return false;
            }
        }
    }
    return true;
}

static uint64_t hash_drawlist(const UcmDrawList *list) {
    const unsigned char *bytes = (const unsigned char *)list->vertices;
    size_t length = (size_t)list->count * sizeof(UcmVertex);
    uint64_t hash = 1469598103934665603ull;
    size_t i;
    for (i = 0; i < length; ++i) {
        hash ^= bytes[i];
        hash *= 1099511628211ull;
    }
    hash ^= list->count;
    return hash;
}

static bool build_fill_cache(const DisplaySurface *surface,
                             uint64_t hash) {
    uint32_t i;
    g_fill_run_count = 0;
    if (g_drawlist.overflow || g_drawlist.count % 6u) return false;
    for (i = 0; i < g_drawlist.count; i += 6u) {
        const UcmVertex *v = &g_drawlist.vertices[i];
        float min_x = v[0].x, max_x = v[0].x;
        float min_y = v[0].y, max_y = v[0].y;
        uint32_t j;
        int x0, x1, y0, y1;
        for (j = 1; j < 6; ++j) {
            if (v[j].x < min_x) min_x = v[j].x;
            if (v[j].x > max_x) max_x = v[j].x;
            if (v[j].y < min_y) min_y = v[j].y;
            if (v[j].y > max_y) max_y = v[j].y;
        }
        x0 = (int)(((min_x + 1.0f) * 640.0f) + 0.5f);
        x1 = (int)(((max_x + 1.0f) * 640.0f) + 0.5f);
        y0 = (int)(((1.0f - max_y) * 360.0f) + 0.5f);
        y1 = (int)(((1.0f - min_y) * 360.0f) + 0.5f);
        if (!append_rectangle(surface, x0, y0, x1, y1,
                              rgba_to_memory_word(v))) return false;
    }
    g_fill_cache_hash = hash;
    g_fill_cache_generation = surface->generation;
    g_fill_cache_valid = true;
    return true;
}

static bool allocate_dcb(void) {
    int32_t result;
    int32_t protection = ORBIS_KERNEL_PROT_CPU_READ |
                         ORBIS_KERNEL_PROT_CPU_RW |
                         ORBIS_KERNEL_PROT_GPU_READ |
                         ORBIS_KERNEL_PROT_GPU_WRITE;
    g_dcb.size = UCM_DCB_BYTES;
    result = sceKernelAllocateDirectMemory(
        0, sceKernelGetDirectMemorySize(), g_dcb.size, UCM_DCB_ALIGNMENT,
        UCM_DCB_MEMORY_TYPE, &g_dcb.direct_offset);
    if (result != 0) return false;
    g_dcb.allocated = true;
    result = sceKernelMapDirectMemory(&g_dcb.mapped, g_dcb.size, protection,
                                      0, g_dcb.direct_offset,
                                      UCM_DCB_ALIGNMENT);
    if (result != 0) return false;
    g_dcb.mapped_ok = true;
    g_dcb.eop_label = (volatile uint64_t *)
        ((uint8_t *)g_dcb.mapped + g_dcb.size - sizeof(uint64_t));
    *g_dcb.eop_label = 1;
    return true;
}

static bool install_detour(Detour *detour, uint64_t target, void *hook,
                           void **trampoline) {
    Detour_Construct(detour, DetourMode_x64);
    *trampoline = Detour_DetourFunction(detour, target, hook);
    return *trampoline != NULL;
}

static void remove_detour(Detour *detour, bool *installed) {
    if (*installed) {
        /* Restore code now, but keep trampoline memory until callbacks drain. */
        Detour_RestoreFunction(detour);
        *installed = false;
    }
}

static void release_detour_storage(Detour *detour) {
    if (detour->StubPtr && detour->StubSize)
        sceKernelMunmap(detour->StubPtr, detour->StubSize);
    if (detour->TrampolinePtr)
        sceKernelMunmap(detour->TrampolinePtr,
                        sizeof(detour->JumpInstructions64));
    memset(detour, 0, sizeof(*detour));
}

static int32_t submit_and_flip_hook(
    uint32_t count, void *dcb_addresses[], uint32_t dcb_sizes[],
    void *ccb_addresses[], uint32_t ccb_sizes[], uint32_t video_handle,
    uint32_t display_index, uint32_t flip_mode, uint64_t flip_arg) {
    VideoOutput output;
    uint64_t pad_state;
    uint64_t hash;
    uint32_t buttons;
    bool connected;
    int output_index;
    int32_t result;

    __atomic_add_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    if (__atomic_load_n(&g_stop_requested, __ATOMIC_ACQUIRE) ||
        !g_overlay || !try_lock_word(&g_submit_lock)) {
        result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                   ccb_addresses, ccb_sizes, video_handle,
                                   display_index, flip_mode, flip_arg);
        __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
        return result;
    }

    memset(&output, 0, sizeof(output));
    lock_word(&g_output_lock);
    output_index = output_index_for((int32_t)video_handle);
    if (output_index >= 0) output = g_outputs[output_index];
    unlock_word(&g_output_lock);

    if (!output.used || !output.surface.supported || display_index >= UCM_MAX_BUFFERS ||
        !output.buffers[display_index] || !output.surface.width ||
        !output.surface.height) {
        result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                   ccb_addresses, ccb_sizes, video_handle,
                                   display_index, flip_mode, flip_arg);
        unlock_word(&g_submit_lock);
        __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
        return result;
    }

    if (!g_overlay->attached) {
        ucm_drawlist_begin(&g_drawlist, g_vertices,
                           (uint32_t)(sizeof(g_vertices) / sizeof(g_vertices[0])),
                           output.surface.width, output.surface.height);
        g_renderer = ucm_drawlist_renderer(&g_drawlist);
        if (!overlay_attach(g_overlay, &g_renderer)) {
            result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                       ccb_addresses, ccb_sizes, video_handle,
                                       display_index, flip_mode, flip_arg);
            unlock_word(&g_submit_lock);
            __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
            return result;
        }
        printf("[TF-UCM] UI attached to verified VideoOut handle %u.\n",
               video_handle);
    }

    ucm_drawlist_begin(&g_drawlist, g_vertices,
                       (uint32_t)(sizeof(g_vertices) / sizeof(g_vertices[0])),
                       output.surface.width, output.surface.height);
    pad_state = __atomic_load_n(&g_pad_state, __ATOMIC_ACQUIRE);
    connected = (pad_state >> 32) != 0;
    buttons = (uint32_t)pad_state;
    overlay_frame(g_overlay, connected, buttons);

    if (!g_overlay->menu.visible || !g_drawlist.count || count >= UCM_MAX_GAME_DCBS ||
        !dcb_addresses || !dcb_sizes || !g_dcb.mapped_ok) {
        result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                   ccb_addresses, ccb_sizes, video_handle,
                                   display_index, flip_mode, flip_arg);
        unlock_word(&g_submit_lock);
        __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
        return result;
    }

    hash = hash_drawlist(&g_drawlist);
    if (!g_fill_cache_valid || g_fill_cache_hash != hash ||
        g_fill_cache_generation != output.surface.generation) {
        if (!build_fill_cache(&output.surface, hash)) {
            g_fill_cache_valid = false;
            result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                       ccb_addresses, ccb_sizes, video_handle,
                                       display_index, flip_mode, flip_arg);
            unlock_word(&g_submit_lock);
            __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
            return result;
        }
    }

    if (g_dcb.in_flight) {
        if (*g_dcb.eop_label != 1u) {
            result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                       ccb_addresses, ccb_sizes, video_handle,
                                       display_index, flip_mode, flip_arg);
            unlock_word(&g_submit_lock);
            __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
            return result;
        }
        g_dcb.in_flight = false;
    }
    if (!g_fill_run_count ||
        (uint64_t)g_fill_run_count * 28u + 24u >
            g_dcb.size - sizeof(uint64_t) - 64u) {
        result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                   ccb_addresses, ccb_sizes, video_handle,
                                   display_index, flip_mode, flip_arg);
        unlock_word(&g_submit_lock);
        __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
        return result;
    }

    {
        GnmCommandBuffer command = sceGnmCmdInit(
            g_dcb.mapped, (uint32_t)(g_dcb.size - sizeof(uint64_t) - 64u),
            NULL, NULL);
        uint64_t framebuffer = (uint64_t)(uintptr_t)output.buffers[display_index];
        uint32_t i;
        bool ok = framebuffer != 0;
        if ((framebuffer & 255u) != 0) ok = false;
        *g_dcb.eop_label = 0;
        for (i = 0; ok && i < g_fill_run_count; ++i) {
            uint64_t target = framebuffer + g_fill_runs[i].offset;
            if (target < framebuffer ||
                !sceGnmDrawCmdFillMemory(&command, target,
                                         g_fill_runs[i].size,
                                         g_fill_runs[i].value)) ok = false;
        }
        if (ok) {
            sceGnmDrawCmdEventWriteEop(
                &command, GNM_CACHE_FLUSH_AND_INV_TS_EVENT,
                (uint64_t)(uintptr_t)g_dcb.eop_label,
                GNM_DATA_SEL_SEND_DATA64, 1u);
            if ((uintptr_t)command.cmdptr <= (uintptr_t)command.beginptr ||
                (uintptr_t)command.cmdptr - (uintptr_t)command.beginptr >
                    UINT32_MAX) ok = false;
        }
        if (!ok) {
            *g_dcb.eop_label = 1;
            result = g_submit_original(count, dcb_addresses, dcb_sizes,
                                       ccb_addresses, ccb_sizes, video_handle,
                                       display_index, flip_mode, flip_arg);
        } else {
            void *all_dcb_addresses[UCM_MAX_GAME_DCBS + 1];
            uint32_t all_dcb_sizes[UCM_MAX_GAME_DCBS + 1];
            uint32_t dcb_bytes =
                (uint32_t)((uintptr_t)command.cmdptr -
                           (uintptr_t)command.beginptr);
            uint32_t j;
            for (j = 0; j < count; ++j) {
                all_dcb_addresses[j] = dcb_addresses[j];
                all_dcb_sizes[j] = dcb_sizes[j];
            }
            all_dcb_addresses[count] = command.beginptr;
            all_dcb_sizes[count] = dcb_bytes;
            g_dcb.in_flight = true;
            result = g_submit_original(count + 1u, all_dcb_addresses,
                                       all_dcb_sizes, ccb_addresses,
                                       ccb_sizes, video_handle, display_index,
                                       flip_mode, flip_arg);
            if (result < 0) {
                g_dcb.in_flight = false;
                *g_dcb.eop_label = 1;
            }
        }
    }
    unlock_word(&g_submit_lock);
    __atomic_sub_fetch(&g_active_callbacks, 1u, __ATOMIC_ACQ_REL);
    return result;
}

static void reset_backend_state(void) {
    memset(g_outputs, 0, sizeof(g_outputs));
    g_overlay = NULL;
    g_fill_cache_valid = false;
    g_fill_run_count = 0;
    g_pad_state = 0;
    g_stop_requested = 0;
    g_active_callbacks = 0;
    g_output_lock = 0;
    g_submit_lock = 0;
    g_next_surface_generation = 0;
}

bool ps4_backend_start(Overlay *overlay) {
    void *trampoline = NULL;
    bool pad_available = false;
    if (!overlay || g_submit_hooked || g_videoout_hooked || g_pad_state_hooked ||
        g_pad_read_hooked || g_dcb.allocated || g_dcb.mapped_ok) return false;
    reset_backend_state();
    g_overlay = overlay;
    if (!allocate_dcb()) {
        ps4_backend_stop();
        return false;
    }

    if (!install_detour(&g_videoout_detour,
                        (uint64_t)(uintptr_t)sceVideoOutRegisterBuffers,
                        (void *)videoout_register_hook, &trampoline)) {
        ps4_backend_stop();
        return false;
    }
    g_videoout_original = (VideoOutRegisterFn)trampoline;
    g_videoout_hooked = true;

    trampoline = NULL;
    if (install_detour(&g_pad_state_detour,
                       (uint64_t)(uintptr_t)scePadReadState,
                       (void *)pad_read_state_hook, &trampoline)) {
        g_pad_state_original = (PadReadStateFn)trampoline;
        g_pad_state_hooked = true;
        pad_available = true;
    }
    trampoline = NULL;
    if (install_detour(&g_pad_read_detour, (uint64_t)(uintptr_t)scePadRead,
                       (void *)pad_read_hook, &trampoline)) {
        g_pad_read_original = (PadReadFn)trampoline;
        g_pad_read_hooked = true;
        pad_available = true;
    }
    if (!pad_available) {
        ps4_backend_stop();
        return false;
    }

    trampoline = NULL;
    if (!install_detour(&g_submit_detour,
                        (uint64_t)(uintptr_t)sceGnmSubmitAndFlipCommandBuffers,
                        (void *)submit_and_flip_hook, &trampoline)) {
        ps4_backend_stop();
        return false;
    }
    g_submit_original = (SubmitAndFlipFn)trampoline;
    g_submit_hooked = true;
    printf("[TF-UCM] GoldHEN GNM/VideoOut and passive DS4 hooks installed.\n");
    return true;
}

void ps4_backend_stop(void) {
    __atomic_store_n(&g_stop_requested, 1u, __ATOMIC_RELEASE);
    /* Restore original entrypoints first. Trampolines stay mapped until all
     * callbacks that already entered the PRX have returned.
     */
    remove_detour(&g_submit_detour, &g_submit_hooked);
    remove_detour(&g_pad_read_detour, &g_pad_read_hooked);
    remove_detour(&g_pad_state_detour, &g_pad_state_hooked);
    remove_detour(&g_videoout_detour, &g_videoout_hooked);

    /* The GoldHEN detour API has no in-flight barrier. Let a frame's already
     * entered callback finish, then wait for callbacks and the GPU EOP label.
     */
    sceKernelUsleep(100000);
    while (__atomic_load_n(&g_active_callbacks, __ATOMIC_ACQUIRE) != 0u)
        sceKernelUsleep(1000);
    release_detour_storage(&g_submit_detour);
    release_detour_storage(&g_pad_read_detour);
    release_detour_storage(&g_pad_state_detour);
    release_detour_storage(&g_videoout_detour);
    if (g_dcb.in_flight && g_dcb.eop_label) {
        uint32_t waited_ms = 0;
        while (*g_dcb.eop_label != 1u && waited_ms < 5000u) {
            sceKernelUsleep(1000);
            ++waited_ms;
        }
        if (*g_dcb.eop_label == 1u) g_dcb.in_flight = false;
        else printf("[TF-UCM] GPU EOP timeout; retaining the command buffer allocation.\n");
    }
    /* If EOP timed out, retain this direct-memory allocation: the GPU may
     * still be consuming it. Leaking 2 MiB is safer than a GPU use-after-free.
     */
    if (!g_dcb.in_flight && g_dcb.mapped_ok) {
        sceKernelMunmap(g_dcb.mapped, g_dcb.size);
        g_dcb.mapped_ok = false;
    }
    if (!g_dcb.in_flight && g_dcb.allocated) {
        sceKernelReleaseDirectMemory(g_dcb.direct_offset, g_dcb.size);
        g_dcb.allocated = false;
    }
    if (!g_dcb.in_flight) memset(&g_dcb, 0, sizeof(g_dcb));
    g_overlay = NULL;
    memset(g_outputs, 0, sizeof(g_outputs));
    g_fill_cache_valid = false;
    g_fill_run_count = 0;
}
