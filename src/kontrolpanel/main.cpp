#include "kontrolpanelservice.h"

#include <KConfigLoader>
#include <KConfigPropertyMap>
#include <KGlobalAccel>
#include <KLocalizedQmlContext>
#include <KLocalizedString>
#include <KSharedConfig>

#include <QAction>
#include <QApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDir>
#include <QFile>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>

namespace
{

void inKontrolPanelComponent(QAction &action, const QString &id, const QString &text)
{
    action.setObjectName(id);
    action.setText(text);
    action.setProperty("componentName", QStringLiteral("konveyor-kontrol-panel"));
    action.setProperty("componentDisplayName", QStringLiteral("Kontrol Panel"));
}

void registerToggleShortcut(QAction &action, Konveyor::KontrolPanelService &service)
{
    inKontrolPanelComponent(action, QStringLiteral("toggle"), QStringLiteral("Open or close the Kontrol Panel"));
    QObject::connect(&action, &QAction::triggered, &service, &Konveyor::KontrolPanelService::Toggle);
    KGlobalAccel::setGlobalShortcut(&action, QList<QKeySequence> {QKeySequence(Qt::Key_Meta), QKeySequence(Qt::ALT | Qt::Key_F1)});
}

void registerKonveyorShortcut(QAction &action, Konveyor::KontrolPanelService &service)
{
    inKontrolPanelComponent(action, QStringLiteral("toggle-konveyor"), QStringLiteral("Turn Konveyor on or off"));
    QObject::connect(&action, &QAction::triggered, &service, &Konveyor::KontrolPanelService::ToggleKonveyor);
    KGlobalAccel::setGlobalShortcut(&action, QKeySequence(Qt::META | Qt::SHIFT | Qt::Key_Backspace));
}

int alreadyRunning()
{
    qCritical("konveyor-kontrol-panel: could not register %s on the session bus; is it already running?",
        Konveyor::KontrolPanelService::serviceName);
    return 1;
}

}

int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    application.setApplicationName(QStringLiteral("konveyor-kontrol-panel"));
    application.setDesktopFileName(QStringLiteral("org.devl0rd.KontrolPanel"));
    application.setQuitOnLastWindowClosed(false);
    application.setQuitLockEnabled(false);
    const QStringList arguments = QApplication::arguments();
    if (arguments.size() != 2) {
        qCritical("usage: konveyor-kontrol-panel DIRECTORY");
        return 2;
    }
    const QDir directory(arguments.at(1));
    QFile schema(directory.filePath(QStringLiteral("config/main.xml")));
    if (!schema.exists()) {
        qCritical("konveyor-kontrol-panel: cannot read %s", qPrintable(schema.fileName()));
        return 1;
    }
    KLocalizedString::setApplicationDomain("plasma_applet_org.devl0rd.portal.launcher");

    Konveyor::KontrolPanelService service;
    const QDBusConnection bus = QDBusConnection::sessionBus();
    if (bus.interface() && bus.interface()->isServiceRegistered(QLatin1String(Konveyor::KontrolPanelService::serviceName))) {
        return alreadyRunning();
    }

    KConfigLoader loader(KSharedConfig::openConfig(QStringLiteral("konveyor/kontrolpanelrc")), &schema);
    KConfigPropertyMap config(&loader);
    config.setNotify(true);
    QObject::connect(&config, &QQmlPropertyMap::valueChanged, &config, [&config] { config.writeConfig(); });

    QQmlApplicationEngine engine;
    engine.setProperty("_kirigamiTheme", QStringLiteral("KirigamiPlasmaStyle"));
    engine.rootContext()->setContextObject(new KLocalizedQmlContext(&engine));
    engine.setInitialProperties(
        {{QStringLiteral("service"), QVariant::fromValue(&service)}, {QStringLiteral("config"), QVariant::fromValue(&config)}});
    const QString main = directory.filePath(QStringLiteral("Main.qml"));
    engine.load(QUrl::fromLocalFile(main));
    if (engine.rootObjects().isEmpty()) {
        qCritical("konveyor-kontrol-panel: could not load %s", qPrintable(main));
        return 1;
    }

    if (!service.registerOn(bus)) {
        return alreadyRunning();
    }
    QAction toggle;
    registerToggleShortcut(toggle, service);
    QAction toggleKonveyor;
    registerKonveyorShortcut(toggleKonveyor, service);
    return QApplication::exec();
}
