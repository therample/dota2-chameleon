# Problems and solutions

**Pictures of skins are missing or look strange**
If an item lists an old picture name, Chameleon looks for the picture inside that item's own folder. A few items may still show a letter
instead of a picture – that means the game has no picture for them.
Open **Settings → Pictures**. Item pictures always come from your game; hero pictures come from Steam first and from your game
as a backup. Press *Clear picture cache* after changing something. If a hero picture from the game has a yellow tint, turn on
*Fix tinted hero pictures*.

**Music (or another section) has only a few things**
Music packs are found through the music folders in your game files. If the section is still short, send the output of
`python -m chameleon.diagnose "<your Dota folder>" --find music` in an issue – it shows exactly what happened to every music-like item.

**A catalog section is empty or has only a few things**
Dota names things differently from version to version. Open an issue and attach the output of
`python -m chameleon.diagnose "<your Dota folder>" --find music` (use the word you are missing, for example `blink`).
Also try *Settings → Rebuild list*.

**The main menu background is a black screen**
Dota only plays a special kind of video. Install the free program [ffmpeg](https://ffmpeg.org/download.html) and choose any
video or picture again – Chameleon prepares it for you. If it is still black, in *World → How to change it* choose
*Replace game video*. You also need the menu files (*World → Download menu files*, needs internet).

**An emblem or effect shows on other players but not on me**
Open Settings → *Emblems and effects on heroes* and choose *On hero items* (or *Both*), press **Apply** and restart Dota 2. The
effect then also shows in matches with other players, but it may look attached to the item. *In the equipped slot* (default)
is the one that appears in your Dota loadout.

**Roshan, ancient or tormentor skin does nothing**
*Settings → Special items* should be *Automatic*. The build report (Settings → Last result) says what was done.

**Gems for Terrorblade / Techies**
Open the hero and choose the **Gems** tab. One gem per hero.

**Dota 2 says the game files are changed / I cannot find an online match**
Press **Restore**, then in Steam choose *Verify integrity of game files*, then **Apply** again. Make sure
*Settings → Allow online play with the mod* is on.

**After a Dota 2 update nothing works**
A note appears at the top – press **Apply** again.

**Skins break after rejoining a match**
Keep *Settings → Keep models after reconnect* on and press **Apply** again.

**The main menu is black after I set a background**
Use a video under about 12 MB / 30 seconds (Chameleon shrinks it if ffmpeg is installed). The background plays in the main menu, not in the hero view.

**Switch one item off**
Open *Selected* and use the switch of that item (it stays in the list but is left out of the next build). *Remove the mod from the game* takes everything out.

**Item pictures are missing**
Settings → *Item pictures from*: *Game*, *Web* (Steam's servers, found by the item's name) or *Game + web*.
