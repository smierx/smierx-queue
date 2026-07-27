# smierx-queue nutzen

Die Queue ist ein Taskmanagement-System mit einem Versprechen: **Durchsatz vorne, nicht Vollständigkeit hinten**. Du arbeitest am Kopf der Queue, die App rückt automatisch nach. Was hinten geparkt liegt, darf liegen.

## Bereiche: Arbeit und Privat

Der Schalter oben im Header wechselt zwischen zwei kompletten Welten: **Arbeit** und **Privat** haben jeweils eigene Tasks, eigene Termine/Blocker, ein eigenes Arbeitszeit-Modell und eigene Kapazität (Privat färbt den Akzent lila). Beide Seiten ticken unabhängig: die automatische Übergabe der einen Seite kümmert sich nicht um die andere, beide können gleichzeitig einen aktiven Task haben.

- Ein privater Task geht auch vormittags: umschalten, aktiv setzen, fertig. Soll die Arbeitsplanung die Unterbrechung sehen, drückst du auf der Arbeits-Seite kurz „⚡ Blocker jetzt".
- Tasks wechseln die Seite im Detail-Modal über das Bereich-Feld und reihen sich drüben hinten ein. Ihre Phasen und ihre Historie wandern mit (zählen also rückwirkend im anderen Bereichs-Export).
- Archiv und Wochen-Export gelten pro Bereich, der Export-Dateiname trägt den Bereich.

## Der Hauptscreen

Von oben nach unten:

- **Tag**: der Zeitstrahl des angezeigten Tages (Default heute) mit Datumsnavigation. Aktive Tasks und Phasen als Balken, Termine und Blocker als feste Blöcke, die Warteliste dahinter.
- **Arbeitszeit**: dein Arbeitszeit-Modell, daraus rechnet die App die freie Kapazität (oben rechts).
- **Läuft gerade** (nur heute): alle Tasks mit Tag `aktiv`, daneben der 🌙 Feierabend-Knopf.
- **Queue**: die Warteliste des angezeigten Tages, `next` zuerst, Rest nach Position. Umsortieren per Drag & Drop, unten das Feld für neue Tasks.
- **Erledigt**: aufklappbares Archiv mit Wiederöffnen und endgültigem Löschen.
- **Export**: Wochen-Export als JSON.

## Tage: vorplanen und nachtragen

Jeder Tag hat seine eigene Queue samt Zeitstrahl. Mit ‹ › neben der Überschrift (oder dem Datums-Feld) blätterst du, „Heute" springt zurück.

- **Zukunftstage** planst du vor: Tasks anlegen, sortieren, Dauer ziehen, Blocker eintragen. Die Warteliste liegt ab dem Arbeitsfenster-Beginn im Zeitstrahl. Keine Jetzt-Linie, kein automatischer Statuswechsel.
- **Vergangene Tage** trägst du nach: Klick auf einen Phasen-Balken korrigiert Von/Bis oder löscht die Phase, „+ Phase" trägt eine neue nach (Task-Auswahl aus heutiger Queue und Archiv), Blocker gehen wie gewohnt. Der Wochen-Export rechnet immer mit dem korrigierten Stand.
- **Rollover:** was am Tagesende nicht erledigt ist, rutscht automatisch an den Kopf der heutigen Queue, sobald die App den neuen Tag sieht (auch geparkte Tasks wandern mit). Hast du den Feierabend-Knopf vergessen, endet die laufende Phase rückwirkend um Mitternacht und der Task steht auf `next`. Die Zeit korrigierst du bei Bedarf nachträglich.
- Einen Task verschiebst du über „Geplant am" im Detail-Modal auf einen anderen Tag (er reiht sich dort hinten ein).

## Tasks

Neuen Task unten in der Queue eintippen, „In die Queue" legt ihn auf den angezeigten Tag. Klick auf einen Titel öffnet das Detail-Modal: Titel, Beschreibung, Dauer in Minuten (Default 60), Geplant-am, die Phasen (mit Bearbeiten/Löschen), rückwirkendes Erledigen und die Tag-Historie. Der ✓-Knopf erledigt einen Task, er wandert ins Archiv statt gelöscht zu werden. Aus dem Archiv holst du ihn per „Wieder öffnen" zurück (er reiht sich heute hinten ein) oder löschst ihn endgültig.

## Tags

Tags setzt du direkt per Klick auf die Chips in der Liste. Es gibt zwei Sorten:

- **Zustand-Tags** schließen sich gegenseitig aus, einen setzen wirft den anderen runter:
  - `aktiv`: läuft gerade, liegt als Balken im Zeitstrahl
  - `next`: kommt als Nächstes dran, steht in Queue und Warteliste vorn
  - `pausiert`, `holding`, `inaktiv`: geparkt, die automatische Übergabe überspringt sie
- **Marker** sind frei kombinierbar: `discussion`, `critical` (färbt die Karte rot)

Jede Tag-Änderung landet in der Historie (sichtbar im Detail-Modal). `support` ist bewusst kein Task-Tag, sondern ein Blocker-Typ: Support-Zeit blockt deinen Tag.

## Zeitstrahl

Ein aktiver Task liegt als grüner Balken im Zeitstrahl, von „aktiv gesetzt" bis Start plus Dauer. Mehrere aktive Tasks stapeln sich in Ebenen. Die Warteliste hängt sich nacheinander dahinter, in einer Ebene, `next` zuerst.

- **Dauer ändern**: am rechten Balkenrand ziehen (5-Minuten-Raster, mindestens 15) oder im Detail-Modal.
- **Überzogen**: läuft ein Task über sein geplantes Ende, färbt sich der Balken gelblich.
- **Phasen bleiben stehen**: jede aktiv-Phase von heute bleibt als blasser Balken sichtbar, auch nach Pausieren oder Erledigen. Wieder aktivieren gibt einen neuen Balken.
- Der Rahmen der Achse kommt aus dem Arbeitszeit-Modell: bei festen Zeiten dein Tagesfenster, im Stunden-Modus 07 bis 16 Uhr. Blöcke außerhalb weiten die Achse, seitlich scrollen geht per Ziehen, Mausrad oder den ‹ › Pfeilen.

## Automatische Übergabe

Die App wechselt Tasks von selbst, als **Übergabe**: läuft nichts mehr in seiner geplanten Zeit, wird der nächste Queue-Task aktiv. Die Regeln:

- Nur wenn schon etwas aktiv ist. Morgens und nach Feierabend startet nichts von selbst, den ersten Task des Tages ziehst du selbst.
- `next` kommt zuerst, dann die Queue-Reihenfolge. Geparkte Tasks (`pausiert`, `holding`, `inaktiv`) bleiben liegen.
- Höchstens ein Wechsel pro Prüfung, aktive Tasks werden nie automatisch beendet. Überziehst du, laufen alt und neu parallel.
- Mitten in einem Blocker passiert nichts.

Die Prüfung läuft als Hintergrund-Schleife im Backend (Default alle 60 Sekunden), der Browser muss dafür nicht offen sein. Die UI pollt zusätzlich alle 30 Sekunden.

## Termine und Blocker

Meetings, Support und andere Unterbrechungen sind keine Tasks, sondern **Zeitblöcke** mit festem Zeitraum. Drei Typen: `meeting`, `blocker`, `support` (türkis). Sie zählen nicht als Arbeitszeit: sie zerteilen aktive Balken optisch, schieben deren geplantes Ende und die ganze Warteliste nach hinten und werden von der freien Kapazität abgezogen.

- **+ Termin/Blocker** legt einen Block per Modal an (Titel, Typ, Von/Bis).
- **⚡ Blocker jetzt** stempelt eine Unterbrechung ab sofort ein (30 Minuten Default) und öffnet direkt das Modal zum Nachbearbeiten. „Bis jetzt" beendet den Block auf die aktuelle Uhrzeit.
- Klick auf einen Block im Zeitstrahl öffnet dasselbe Modal, dort auch Löschen.

Wiederholungen (z.B. ein Daily) gibt es nicht, jeder Block ist ein Einzeleintrag.

## Feierabend

Der 🌙-Knopf neben „Läuft gerade" setzt alle aktiven Tasks auf `next`. Ihre aktiv-Phasen enden und bleiben als Balken stehen, die Übergabe bleibt danach still. Am nächsten Morgen ziehst du den ersten Task wieder selbst.

## Arbeitszeit

Im Arbeitszeit-Panel wählst du deinen Modus:

- **Stunden pro Tag**: z.B. 8 Stunden, ohne feste Lage.
- **Feste Zeiten**: pro Wochentag ein Fenster, z.B. Mo 08:00 bis 16:30, freie Tage bleiben leer.

Freie Kapazität = Arbeitszeit minus Termine/Blocker, angezeigt oben rechts.

## Wochen-Export

Die Export-Sektion lädt eine Kalenderwoche als JSON herunter (`smierx-queue-JJJJ-WXX.json`): alle aktiv-Phasen mit Netto-Minuten (Blocker-Zeit abgezogen, offene Phasen bis jetzt gerechnet und als `offen` markiert), erledigte Tasks, Blocker und eine Zusammenfassung (gearbeitet, geblockt, erledigt).

Ehrlich einordnen: der Export misst **geplante Aktiv-Zeit, keine belegte Arbeit**. Die automatische Übergabe erzeugt auch Phasen, in denen du real etwas anderes getan hast. Die Zahlen sind Orientierung, kein Timesheet.
