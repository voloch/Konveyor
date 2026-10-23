#pragma once

#include <KConfigGroup>

#include <QStringList>

namespace Konveyor
{

// Konveyor effect ids from available whose <id>Enabled entry in the [Plugins] group of kwinrc is true, in available order.
QStringList konveyorEffectsToLoad(const QStringList &available, const KConfigGroup &plugins);

// Turns the Konveyor effect off if KWin has it loaded, otherwise loads the Konveyor effects kwinrc enables. Returns at once; ignored while
// the last call is unfinished.
void toggleKonveyor();

}
