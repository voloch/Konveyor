#include "fractional-scale-v1-client-protocol.h"
#include "xdgclient.h"

#include <cstdio>
#include <list>
#include <string>

namespace
{

struct Output
{
    std::string name;
};

struct Client
{
    wl_display *display = nullptr;
    XdgGlobals globals;
    std::list<Output> outputs;
    wp_fractional_scale_manager_v1 *scaleManager = nullptr;
    wl_surface *surface = nullptr;
    xdg_surface *xdgSurface = nullptr;
    xdg_toplevel *toplevel = nullptr;
    wl_buffer *buffer = nullptr;
    bool mapped = false;
    bool closed = false;
    int width = 600;
    int height = 400;
};

void outputGeometry(void *, wl_output *, int32_t, int32_t, int32_t, int32_t, int32_t, const char *, const char *, int32_t) { }

void outputMode(void *, wl_output *, uint32_t, int32_t, int32_t, int32_t) { }

void outputDone(void *, wl_output *) { }

void outputScale(void *, wl_output *, int32_t) { }

void outputName(void *data, wl_output *, const char *name)
{
    static_cast<Output *>(data)->name = name;
}

void outputDescription(void *, wl_output *, const char *) { }

constexpr wl_output_listener outputListener {outputGeometry, outputMode, outputDone, outputScale, outputName, outputDescription};

void bindOutput(void *data, wl_registry *registry, uint32_t name, const char *interface, uint32_t version)
{
    auto *client = static_cast<Client *>(data);
    if (std::strcmp(interface, wl_output_interface.name) == 0) {
        auto *output = static_cast<wl_output *>(wl_registry_bind(registry, name, &wl_output_interface, std::min(version, 4u)));
        wl_output_add_listener(output, &outputListener, &client->outputs.emplace_back());
    } else if (std::strcmp(interface, wp_fractional_scale_manager_v1_interface.name) == 0) {
        client->scaleManager = static_cast<wp_fractional_scale_manager_v1 *>(
            wl_registry_bind(registry, name, &wp_fractional_scale_manager_v1_interface, 1));
    }
}

constexpr wl_registry_listener registryListener {bindOutput, ignoreGlobalRemoval};

void report(const char *event, wl_output *output)
{
    const auto *entry = static_cast<const Output *>(wl_output_get_user_data(output));
    std::printf("%s %s\n", event, entry->name.c_str());
    std::fflush(stdout);
}

void surfaceEnter(void *, wl_surface *, wl_output *output)
{
    report("ENTER", output);
}

void surfaceLeave(void *, wl_surface *, wl_output *output)
{
    report("LEAVE", output);
}

void surfaceScale(void *, wl_surface *, int32_t) { }

void surfaceTransform(void *, wl_surface *, uint32_t) { }

constexpr wl_surface_listener surfaceListener {surfaceEnter, surfaceLeave, surfaceScale, surfaceTransform};

void preferredScale(void *, wp_fractional_scale_v1 *, uint32_t scale)
{
    std::printf("SCALE %u\n", scale);
    std::fflush(stdout);
}

constexpr wp_fractional_scale_v1_listener scaleListener {preferredScale};

// Like Chromium, answer every configure with a freshly rendered frame: KWin only runs its
// geometry restrictions on a commit that acknowledges a configure.
void surfaceConfigure(void *data, xdg_surface *surface, uint32_t serial)
{
    auto *client = static_cast<Client *>(data);
    xdg_surface_ack_configure(surface, serial);
    const int width = client->width > 0 ? client->width : 600;
    const int height = client->height > 0 ? client->height : 400;
    wl_buffer *previous = client->buffer;
    client->buffer = makeSolidBuffer(client->globals.shm, width, height, 0xff3050b0u);
    wl_surface_attach(client->surface, client->buffer, 0, 0);
    wl_surface_damage_buffer(client->surface, 0, 0, width, height);
    if (previous) {
        wl_buffer_destroy(previous);
    }
    wl_surface_commit(client->surface);
    if (!client->mapped) {
        client->mapped = true;
        std::puts("READY");
        std::fflush(stdout);
    }
}

constexpr xdg_surface_listener xdgSurfaceListener {surfaceConfigure};

void toplevelConfigure(void *data, xdg_toplevel *, int32_t width, int32_t height, wl_array *)
{
    auto *client = static_cast<Client *>(data);
    client->width = width;
    client->height = height;
}

void toplevelClose(void *data, xdg_toplevel *)
{
    static_cast<Client *>(data)->closed = true;
}

void toplevelBounds(void *, xdg_toplevel *, int32_t, int32_t) { }

void toplevelCapabilities(void *, xdg_toplevel *, wl_array *) { }

constexpr xdg_toplevel_listener toplevelListener {toplevelConfigure, toplevelClose, toplevelBounds, toplevelCapabilities};

}

int main(int argc, char **argv)
{
    if (argc != 2) {
        return 2;
    }
    Client client;
    client.display = wl_display_connect(nullptr);
    if (!client.display) {
        return 3;
    }
    if (!bindGlobals(client.display, client.globals)) {
        return 4;
    }
    wl_registry *registry = wl_display_get_registry(client.display);
    wl_registry_add_listener(registry, &registryListener, &client);
    wl_display_roundtrip(client.display);
    wl_display_roundtrip(client.display);
    client.surface = wl_compositor_create_surface(client.globals.compositor);
    wl_surface_add_listener(client.surface, &surfaceListener, &client);
    if (client.scaleManager) {
        wp_fractional_scale_v1_add_listener(wp_fractional_scale_manager_v1_get_fractional_scale(client.scaleManager, client.surface),
                                            &scaleListener, nullptr);
    }
    client.xdgSurface = xdg_wm_base_get_xdg_surface(client.globals.shell, client.surface);
    xdg_surface_add_listener(client.xdgSurface, &xdgSurfaceListener, &client);
    client.toplevel = xdg_surface_get_toplevel(client.xdgSurface);
    xdg_toplevel_add_listener(client.toplevel, &toplevelListener, &client);
    xdg_toplevel_set_title(client.toplevel, argv[1]);
    xdg_toplevel_set_app_id(client.toplevel, "konveyor-output-tracking-test");
    wl_surface_commit(client.surface);
    while (!client.closed && wl_display_dispatch(client.display) != -1) { }
    return 0;
}
