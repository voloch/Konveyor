#pragma once

#include <KConfigGroup>

#include <QStringList>

namespace Konveyor
{

// Konveyor effect ids from available whose <id>Enabled entry in the [Plugins] group of kwinrc is true, in available order.
QStringList konveyorEffectsToLoad(const QStringList &available, const KConfigGroup &plugins);

// The panel-swap helper that turning Konveyor off or on starts, detached, with "off" or "on".
void setPanelSwapHelper(const QString &path);

// Starts the panel-swap helper with "on" if KWin has a Konveyor effect loaded; for a start of the Kontrol Panel after logging in. Returns
// at once.
void swapPanelBackIfKonveyorIsLoaded();

// Turns the Konveyor effect off if KWin has it loaded, otherwise loads the Konveyor effects kwinrc enables, then starts the panel-swap
// helper with "off" or, if an effect loaded, "on". Returns at once; ignored while the last call is unfinished.
void toggleKonveyor();

}
