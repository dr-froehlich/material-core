# tools

Hilfsskripte rund um die Material-Erstellung, die nicht Teil des `matctl`-CLI
sind.

## render_session.py

Wandelt ein Claude-Code-Session-Transkript (`.jsonl`) in eine Quarto-Seite
(`.qmd`) um — z. B. um eine gelungene Arbeitssitzung als Lehrbeispiel
weiterzugeben. Prompts werden als Callouts hervorgehoben, Datei-Edits als
farbige `diff`-Blöcke, Bash-Kommandos samt (einklappbarer) Ausgabe als
Codeblöcke.

### Bedienung

```bash
python3 tools/render_session.py <transkript.jsonl> <ausgabe.qmd> \
  --title "Titel der Session"
```

Transkripte liegen unter `~/.claude/projects/<projektpfad>/<session-id>.jsonl`.
Die erzeugte `.qmd` legt man in das jeweilige Kursverzeichnis und rendert sie
mit dem normalen `quarto render`; sie nutzt automatisch das Brand-Theme und
ergibt farbige Diffs in HTML wie im Typst-PDF.

### Erkenntnisse (warum das Skript das tut, was es tut)

- **ANSI-/Steuerzeichen müssen raus.** Bash-Ausgaben im Transkript enthalten
  rohe ANSI-Farbcodes (`\x1b[...m`) und Carriage-Returns (`\r`). Quartos
  Markdown-Reader verschluckt dadurch ganze Blöcke (Symptom: „Div … unclosed,
  closing implicitly", letzter Absatz fehlt im HTML). `clean()` strippt
  CSI-/OSC-Sequenzen und Steuerzeichen vor dem Rendern.
- **Code-Fences brauchen dynamische Backtick-Länge.** Edits an `.qmd`-Dateien
  enthalten selbst ```` ``` ````-Fences und `:::`-Divs. Der umschließende Fence
  muss länger sein als jeder Backtick-Lauf im Inhalt (`fence_ticks()`), sonst
  bricht die Darstellung auseinander.
- **„Thinking" ist nicht im Klartext verfügbar.** Claudes interne Überlegungen
  liegen im Transkript nur verschlüsselt/signiert vor (leeres `thinking`-Feld
  plus `signature`). Sie lassen sich daher nicht rendern; die Einleitung
  erwähnt sie nur, wenn tatsächlich welche vorhanden sind.
