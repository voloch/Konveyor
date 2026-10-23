#include "plugin/konveyoreffect_p.h"

#include "config/log.h"
#include "layout/common/geometry.h"

namespace Konveyor
{

void KonveyorEffect::disable()
{
    if (d->disabling) {
        return;
    }
    const QStringList loaded = KWin::effects->loadedEffects();
    const auto self = std::ranges::find_if(loaded, [this](const QString &name) { return KWin::effects->findEffect(name) == this; });
    if (self == loaded.end()) {
        qCWarning(lcKonveyor) << "konveyor: cannot disable, this effect is not among the loaded effects";
        return;
    }
    d->disabling = true;
    const QList<Layout::WindowState> states = readEngine().windowStates();
    d->applier.restoreAppearance(states);

    const QList<KWin::LogicalOutput *> outputs = KWin::workspace()->outputs();
    QList<QRectF> screens;
    for (const KWin::LogicalOutput *output : outputs) {
        screens.append(output->geometryF());
    }
    QHash<const KWin::LogicalOutput *, int> placed;
    for (const Layout::WindowState &state : states) {
        KWin::Window *window = d->windows.windowOf(state.id);
        if (!window || window->isFullScreen() || window->isRequestedFullScreen() || window->isMinimized()) {
            continue;
        }
        const QRectF frame = window->moveResizeGeometry();
        if (frame.isEmpty() || std::ranges::any_of(screens, [&frame](const QRectF &screen) { return frame.intersects(screen); })) {
            continue;
        }
        KWin::LogicalOutput *home = d->outputs.outputNamed(state.output);
        if (!home) {
            home = outputs.value(Layout::nearestOutputIndex(frame.center(), screens));
        }
        if (home) {
            window->moveResize(Layout::unparkedFrame(frame.size(), OutputRegistry::infoOf(home).workArea, placed[home]++));
        }
    }

    // Unload after this D-Bus call has been answered: the effect, and the service that received the call, go away with it.
    QMetaObject::invokeMethod(KWin::effects, [id = *self] { KWin::effects->unloadEffect(id); }, Qt::QueuedConnection);
}

}
