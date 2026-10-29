#include "konveyorswitch.h"

#include <KSharedConfig>

#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusVariant>
#include <QProcess>

#include <algorithm>
#include <functional>
#include <memory>

namespace Konveyor
{

namespace
{

const QString effectIdPrefix = QStringLiteral("konveyor_effect");

bool pending = false;
QString panelSwap;

void whenFinished(const QDBusMessage &message, std::function<void(QDBusPendingCallWatcher &)> then)
{
    auto *watcher = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message));
    QObject::connect(watcher, &QDBusPendingCallWatcher::finished, watcher, [watcher, then = std::move(then)] {
        then(*watcher);
        watcher->deleteLater();
    });
}

QDBusMessage kwinEffects(const QString &interface, const QString &member)
{
    return QDBusMessage::createMethodCall(QStringLiteral("org.kde.KWin"), QStringLiteral("/Effects"), interface, member);
}

QDBusMessage kwinEffectProperty(const QString &name)
{
    QDBusMessage message = kwinEffects(QStringLiteral("org.freedesktop.DBus.Properties"), QStringLiteral("Get"));
    message << QStringLiteral("org.kde.kwin.Effects") << name;
    return message;
}

void warnIfFailed(const QDBusPendingCallWatcher &watcher, const char *what)
{
    if (watcher.isError()) {
        qWarning("konveyor-kontrol-panel: %s failed: %s", what, qPrintable(watcher.error().message()));
    }
}

bool hasKonveyorEffect(const QStringList &ids)
{
    return std::any_of(ids.cbegin(), ids.cend(), [](const QString &id) { return id.startsWith(effectIdPrefix); });
}

// Never blocks or fails the toggle: the panel keeps its widgets if the helper is missing or does not start.
void swapPanel(const QString &mode)
{
    if (!QProcess::startDetached(panelSwap, {mode})) {
        qWarning("konveyor-kontrol-panel: could not start %s %s", qPrintable(panelSwap), qPrintable(mode));
    }
}

void turnOff()
{
    whenFinished(QDBusMessage::createMethodCall(QStringLiteral("org.kde.Konveyor"), QStringLiteral("/Konveyor"),
                     QStringLiteral("org.kde.Konveyor"), QStringLiteral("Disable")),
        [](QDBusPendingCallWatcher &watcher) {
            warnIfFailed(watcher, "turning Konveyor off");
            pending = false;
            if (!watcher.isError()) {
                swapPanel(QStringLiteral("off"));
            }
        });
}

void turnOn(const QStringList &available)
{
    const KSharedConfigPtr kwinrc = KSharedConfig::openConfig(QStringLiteral("kwinrc"));
    kwinrc->reparseConfiguration();
    const QStringList toLoad = konveyorEffectsToLoad(available, kwinrc->group(QStringLiteral("Plugins")));
    if (toLoad.isEmpty()) {
        qWarning("konveyor-kontrol-panel: kwinrc enables no installed Konveyor effect, nothing to turn on");
        pending = false;
        return;
    }
    struct Loading
    {
        int remaining;
        bool anyLoaded = false;
    };
    const auto loading = std::make_shared<Loading>(Loading {static_cast<int>(toLoad.size())});
    for (const QString &id : toLoad) {
        QDBusMessage load = kwinEffects(QStringLiteral("org.kde.kwin.Effects"), QStringLiteral("loadEffect"));
        load << id;
        whenFinished(load, [loading](QDBusPendingCallWatcher &watcher) {
            warnIfFailed(watcher, "loading a Konveyor effect");
            const QDBusPendingReply<bool> loaded = watcher;
            loading->anyLoaded = loading->anyLoaded || (!loaded.isError() && loaded.value());
            pending = --loading->remaining > 0;
            if (!pending && loading->anyLoaded) {
                swapPanel(QStringLiteral("on"));
            }
        });
    }
}

}

void setPanelSwapHelper(const QString &path)
{
    panelSwap = path;
}

void swapPanelBackIfKonveyorIsLoaded()
{
    whenFinished(kwinEffectProperty(QStringLiteral("loadedEffects")), [](QDBusPendingCallWatcher &watcher) {
        const QDBusPendingReply<QDBusVariant> loaded = watcher;
        if (loaded.isError()) {
            warnIfFailed(watcher, "asking KWin for the loaded effects");
        } else if (hasKonveyorEffect(loaded.value().variant().toStringList())) {
            swapPanel(QStringLiteral("on"));
        }
    });
}

QStringList konveyorEffectsToLoad(const QStringList &available, const KConfigGroup &plugins)
{
    QStringList toLoad;
    for (const QString &id : available) {
        if (id.startsWith(effectIdPrefix) && plugins.readEntry(id + QStringLiteral("Enabled"), false)) {
            toLoad.append(id);
        }
    }
    return toLoad;
}

void toggleKonveyor()
{
    if (pending) {
        return;
    }
    pending = true;
    whenFinished(kwinEffectProperty(QStringLiteral("loadedEffects")), [](QDBusPendingCallWatcher &watcher) {
        const QDBusPendingReply<QDBusVariant> loaded = watcher;
        if (loaded.isError()) {
            warnIfFailed(watcher, "asking KWin for the loaded effects");
            pending = false;
            return;
        }
        if (hasKonveyorEffect(loaded.value().variant().toStringList())) {
            turnOff();
            return;
        }
        whenFinished(kwinEffectProperty(QStringLiteral("listOfEffects")), [](QDBusPendingCallWatcher &installed) {
            const QDBusPendingReply<QDBusVariant> available = installed;
            if (available.isError()) {
                warnIfFailed(installed, "asking KWin for the installed effects");
                pending = false;
                return;
            }
            turnOn(available.value().variant().toStringList());
        });
    });
}

}
