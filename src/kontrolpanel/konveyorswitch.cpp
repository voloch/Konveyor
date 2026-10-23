#include "konveyorswitch.h"

namespace Konveyor
{

QStringList konveyorEffectsToLoad(const QStringList &available, const KConfigGroup &plugins)
{
    QStringList toLoad;
    for (const QString &id : available) {
        if (id.startsWith(QStringLiteral("konveyor_effect")) && plugins.readEntry(id + QStringLiteral("Enabled"), false)) {
            toLoad.append(id);
        }
    }
    return toLoad;
}

}
